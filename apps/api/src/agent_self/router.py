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
    conv = (
        await db.execute(
            select(AgentConversation).where(AgentConversation.id == conv_id)
        )
    ).scalar_one_or_none()
    if conv is None or conv.host_user_id != current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="会话不存在或不属于你")

    async def event_stream():
        try:
            async for token in stream_and_persist(
                db,
                conversation=conv,
                user_message_content=payload.content,
            ):
                yield _sse_event(token, event="token")
            yield _sse_event(f'{{"conversation_id": {conv.id}}}', event="done")
        except Exception as e:
            yield _sse_event(f"{type(e).__name__}: {e}", event="error")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx / Railway 反代不缓冲
        },
    )
