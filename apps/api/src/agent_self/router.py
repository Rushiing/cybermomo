"""
08 · 跟自己 Agent 对话 · API

- POST /api/me/agent/conversations                       新建一个空会话
- GET  /api/me/agent/conversations                       本人会话列表
- GET  /api/me/agent/conversations/{id}                  单会话 metadata
- GET  /api/me/agent/conversations/{id}/messages         历史消息
- POST /api/me/agent/conversations/{id}/messages         发消息 → SSE 流回复

铁律(router 层强制):
- 所有 endpoint 都校验 conversation.host_user_id == current_user.id
- 前端拿不到任何别的用户的 conversation
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import BackgroundTasks

from src.agent_self.engine import (
    get_or_create_conversation,
    stream_and_persist,
)
from src.agent_self.models import AgentConversation, AgentConversationMessage
from src.auth.deps import CurrentUser
from src.auth.models import User
from src.shared.db import get_session

router = APIRouter()


# ========================================
# Schemas
# ========================================


class CreateConversationRequest(BaseModel):
    scope: Literal["room", "plaza", "revisit", "general"] = "general"
    title: Optional[str] = None
    context_refs: Optional[dict[str, Any]] = None
    # 可选:开场即跑一条用户消息(便于"从简报开聊"场景一次性建会话+发首问)
    first_user_message: Optional[str] = Field(default=None, max_length=4000)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    host_user_id: int
    scope: str
    title: Optional[str] = None
    context_refs: Optional[dict[str, Any]] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
    # 列表用 — 最后一条消息预览(可空)
    last_message_preview: Optional[str] = None


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    turn: int
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class RedispatchRequest(BaseModel):
    """从「跟我 Agent 聊聊」对话里发起再派 — direction_hint 是宿主刚跟 Agent
    沉淀的新方向(短文本,会注入下一场 agent 互聊的 prompt)"""
    direction_hint: str = Field(min_length=1, max_length=500)


class RedispatchResponse(BaseModel):
    ok: bool
    summary_id: int


# ========================================
# 会话:新建 / 列表 / 详情
# ========================================


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    payload: CreateConversationRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    新建一个 Agent 对话会话。
    传 first_user_message 会同步落第一条 user message(便于"决策 → 跳转 → 续聊"流程),
    但 assistant 的首回复仍走 SSE endpoint(避免 POST 同时返回 JSON + 流)。
    """
    conv = await get_or_create_conversation(
        db,
        host_user_id=current_user.id,
        conversation_id=None,
        scope=payload.scope,
        title=payload.title,
        context_refs=payload.context_refs,
    )
    return ConversationResponse(
        id=conv.id,
        host_user_id=conv.host_user_id,
        scope=conv.scope,
        title=conv.title,
        context_refs=conv.context_refs,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
    )


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """本人会话列表,按最近活跃倒序"""
    rows = (
        await db.execute(
            select(AgentConversation)
            .where(AgentConversation.host_user_id == current_user.id)
            .order_by(
                desc(AgentConversation.last_message_at),
                desc(AgentConversation.created_at),
            )
        )
    ).scalars().all()

    # 拉每个会话最后一条消息预览(简单做法:循环 SQL,N 小不优化)
    out: list[ConversationResponse] = []
    for c in rows:
        last_msg = (
            await db.execute(
                select(AgentConversationMessage)
                .where(AgentConversationMessage.conversation_id == c.id)
                .order_by(desc(AgentConversationMessage.turn))
                .limit(1)
            )
        ).scalar_one_or_none()
        preview = None
        if last_msg:
            preview = (last_msg.content or "")[:80]
        out.append(ConversationResponse(
            id=c.id,
            host_user_id=c.host_user_id,
            scope=c.scope,
            title=c.title,
            context_refs=c.context_refs,
            last_message_at=c.last_message_at,
            created_at=c.created_at,
            last_message_preview=preview,
        ))
    return out


@router.get("/conversations/{conv_id}", response_model=ConversationResponse)
async def get_conversation(
    conv_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    conv = (
        await db.execute(
            select(AgentConversation).where(AgentConversation.id == conv_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.host_user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在或不属于你")
    return ConversationResponse(
        id=conv.id,
        host_user_id=conv.host_user_id,
        scope=conv.scope,
        title=conv.title,
        context_refs=conv.context_refs,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
    )


@router.get(
    "/conversations/{conv_id}/messages",
    response_model=list[MessageResponse],
)
async def list_messages(
    conv_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    conv = (
        await db.execute(
            select(AgentConversation).where(AgentConversation.id == conv_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.host_user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在或不属于你")

    rows = (
        await db.execute(
            select(AgentConversationMessage)
            .where(AgentConversationMessage.conversation_id == conv_id)
            .order_by(AgentConversationMessage.turn)
        )
    ).scalars().all()
    return rows


# ========================================
# 发消息 — SSE 流式回复
# ========================================


def _sse_event(data: str, event: Optional[str] = None) -> bytes:
    """组装一个 SSE event(text/event-stream 格式)"""
    out = ""
    if event:
        out += f"event: {event}\n"
    # 多行内容每行都要 'data: ' 前缀
    for line in data.split("\n"):
        out += f"data: {line}\n"
    out += "\n"
    return out.encode("utf-8")


@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: int,
    payload: SendMessageRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    用户发一条消息,以 SSE 流式返回 Agent 回复。

    返回格式(text/event-stream):
      event: token
      data: <增量>

      event: done
      data: {"conversation_id": N}

    出错时:
      event: error
      data: <错误信息>

    前端用 EventSource 或 fetch+ReadableStream 解码即可。
    """
    # 用注入的 db 做一次性 host scope 校验(快,在 streaming 之前)
    conv = (
        await db.execute(
            select(AgentConversation).where(AgentConversation.id == conv_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.host_user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在或不属于你")

    # stream_and_persist 内部自己分阶段持/释 SessionLocal(避免长占连接),
    # 这里只需要透传 conversation_id / host_user_id / content
    captured_conv_id = conv_id
    captured_user_id = current_user.id
    captured_user_message = payload.content

    async def event_stream():
        try:
            async for token in stream_and_persist(
                conversation_id=captured_conv_id,
                host_user_id=captured_user_id,
                user_message_content=captured_user_message,
            ):
                yield _sse_event(token, event="token")
            yield _sse_event(
                f'{{"conversation_id": {captured_conv_id}}}', event="done"
            )
        except Exception as e:
            print(f"[agent_self] stream failed conv={captured_conv_id}: {e}")
            yield _sse_event(f"{type(e).__name__}: {e}", event="error")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx / Railway 反代不缓冲
        },
    )


# ========================================
# 从对话里直接触发再派(scope=room 才能用)
# ========================================


@router.post(
    "/conversations/{conv_id}/redispatch",
    response_model=RedispatchResponse,
)
async def trigger_redispatch_from_conversation(
    conv_id: int,
    payload: RedispatchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    在「跟我 Agent 聊聊」对话里点「用这个方向再派一次」时调用。
    跟 /api/summary/{id}/decision (decision=re_dispatch) 区别:
    - 这条路径**不再次写入 SummaryDecision**(那张简报已经决策过 chat_with_my_agent)
    - 直接调用 run_redispatch_for_summary,direction_hint 注入下一场 agent 互聊的 prompt

    需要 conversation.scope == 'room' 且 context_refs 里有 summary_id。
    """
    conv = (
        await db.execute(
            select(AgentConversation).where(AgentConversation.id == conv_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.host_user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在或不属于你")
    if conv.scope != "room":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="只有「简报后调方向」对话能触发再派,这场不是",
        )
    refs = conv.context_refs or {}
    summary_id = refs.get("summary_id")
    if not summary_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="这场对话没记下简报 id,改不了再派",
        )

    from src.match.pipeline import run_redispatch_for_summary

    background_tasks.add_task(
        run_redispatch_for_summary,
        summary_id=int(summary_id),
        requester_user_id=current_user.id,
        direction_hint=payload.direction_hint,
    )

    return RedispatchResponse(ok=True, summary_id=int(summary_id))
