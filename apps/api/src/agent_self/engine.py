"""
08 · 跟自己 Agent 对话 · 对话引擎

核心入口:
- get_or_create_conversation(...) → AgentConversation
- seed_conversation_opener(...)    → 给空对话种第一条 assistant 消息(回访 / room 决策场景)
- stream_agent_reply(...)          → async generator,流式生成 assistant 回复
- persist_user_message(...)        → 用户发消息时落库(在 stream 开始前调)
- embed_message_async(...)         → 单条消息生成 embedding 并写回(stream 完成后调)

流程(POST /api/me/agent/conversations/{id}/messages):
  1. persist_user_message(user 输入)      → DB 立刻有 user message
  2. async for token in stream_agent_reply(...): yield token  (SSE)
  3. stream done → assistant message 落库 + embedding 异步回填
  4. update conversation.last_message_at

铁律体现:
- system prompt 永远经 prompts.build_system_prompt(),已过滤敏感字段
- 不写 agent_chat_messages.private_signals(对方的)进任何 prompt
- conversation.host_user_id 严格校验在 router 层
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_self.models import AgentConversation, AgentConversationMessage
from src.agent_self.prompts import build_system_prompt
from src.agent_self.rag import retrieve_context
from src.llm.gateway import _get_client, _model_for_role, llm_embed
from src.llm.models import LlmCallLog
from src.md.models import MdDocument


# ========================================
# 会话生命周期
# ========================================

async def get_or_create_conversation(
    db: AsyncSession,
    *,
    host_user_id: int,
    conversation_id: Optional[int] = None,
    scope: str = "general",
    title: Optional[str] = None,
    context_refs: Optional[dict] = None,
) -> AgentConversation:
    """
    传 conversation_id 拿现有(校验 host scope);不传则新建。

    用法:
      - 用户主动开新对话(右下浮动 Agent 第一次点)→ conversation_id=None, scope='general'
      - 在简报上点「跟我聊聊」→ conversation_id=None, scope='room',
        context_refs={"summary_id": ..., "agent_chat_id": ...}
      - 续聊已有对话 → conversation_id=N
    """
    if conversation_id is not None:
        conv = (
            await db.execute(
                select(AgentConversation).where(AgentConversation.id == conversation_id)
            )
        ).scalar_one_or_none()
        if conv is None:
            raise ValueError(f"conversation {conversation_id} not found")
        if conv.host_user_id != host_user_id:
            raise PermissionError("conversation does not belong to this user")
        return conv

    conv = AgentConversation(
        host_user_id=host_user_id,
        scope=scope,
        title=title,
        context_refs=context_refs,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def _next_turn(db: AsyncSession, conversation_id: int) -> int:
    """拿这个会话下一个 turn 编号(从 1 起)"""
    last = (
        await db.execute(
            select(AgentConversationMessage.turn)
            .where(AgentConversationMessage.conversation_id == conversation_id)
            .order_by(desc(AgentConversationMessage.turn))
            .limit(1)
        )
    ).scalar_one_or_none()
    return (last or 0) + 1


# ========================================
# 消息落库
# ========================================

async def persist_user_message(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    content: str,
) -> AgentConversationMessage:
    """用户发消息 — stream 开始前立刻落库,确保历史完整"""
    msg = AgentConversationMessage(
        conversation_id=conversation.id,
        role="user",
        content=content,
        turn=await _next_turn(db, conversation.id),
    )
    db.add(msg)
    conversation.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return msg


async def persist_assistant_message(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    content: str,
) -> AgentConversationMessage:
    """assistant stream 完成后落库 — content 是完整拼接后的文本"""
    msg = AgentConversationMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        turn=await _next_turn(db, conversation.id),
    )
    db.add(msg)
    conversation.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return msg


async def persist_system_message(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    content: str,
) -> AgentConversationMessage:
    """system 种子消息(Agent 主动起头的开场白) — 标 role='assistant' 给前端展示统一"""
    return await persist_assistant_message(
        db, conversation=conversation, content=content
    )


# ========================================
# Embedding 异步回填
# ========================================

async def embed_message_async(
    db: AsyncSession,
    *,
    message: AgentConversationMessage,
) -> None:
    """给单条消息生成 embedding 并写回。失败不影响主流程。"""
    try:
        if not (message.content or "").strip():
            return
        resp = await llm_embed(
            message.content,
            user_id=None,  # message 没有直接 user_id;conversation 上才有
            related_table="agent_conversation_messages",
            related_id=message.id,
        )
        message.embedding = resp.vector
        await db.commit()
    except Exception as e:
        print(f"[agent_self] embed msg {message.id} failed: {e}")
        await db.rollback()


# ========================================
# 检索上下文
# ========================================

async def _load_host_profile(db: AsyncSession, user_id: int) -> Optional[dict]:
    """拉宿主 active .md 的 profile_json"""
    md = (
        await db.execute(
            select(MdDocument).where(
                MdDocument.user_id == user_id,
                MdDocument.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    return md.profile_json if md else None


async def _load_recent_history(
    db: AsyncSession, conversation_id: int, *, max_msgs: int = 12
) -> list[AgentConversationMessage]:
    """拉同会话最近 N 条消息(含当前用户消息),按 turn 升序返回"""
    rows = (
        await db.execute(
            select(AgentConversationMessage)
            .where(AgentConversationMessage.conversation_id == conversation_id)
            .order_by(desc(AgentConversationMessage.turn))
            .limit(max_msgs)
        )
    ).scalars().all()
    return list(reversed(rows))


# ========================================
# 流式生成(SSE)
# ========================================

async def stream_agent_reply(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    user_message_content: str,
) -> AsyncGenerator[str, None]:
    """
    生成 assistant 回复的流式 token。**调用方负责**:
    1. 在调用本函数前先 persist_user_message(...)
    2. 拿完整 stream 后 persist_assistant_message(...) + embed_message_async(...)

    本函数只负责:RAG 检索 → 拼 prompt → 流式调 DashScope → yield tokens。

    Yields:
        str: 每次一段 token 增量(可能是单字、词、甚至空字符串心跳)
    """
    profile_json = await _load_host_profile(db, conversation.host_user_id)
    chunks = await retrieve_context(
        db,
        user_id=conversation.host_user_id,
        query=user_message_content,
        exclude_conversation_id=conversation.id,
    )
    system_prompt = build_system_prompt(profile_json=profile_json, chunks=chunks)

    history = await _load_recent_history(db, conversation.id)

    # 组装 OpenAI 格式 messages
    api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in history:
        # system role 在 DB 里其实不会出现(persist_system_message 写成 assistant)
        # 但安全起见过滤一下
        if m.role in ("user", "assistant"):
            api_messages.append({"role": m.role, "content": m.content})

    client = _get_client()
    model = _model_for_role("host_agent")

    full_text_parts: list[str] = []
    error: Optional[str] = None
    input_tokens = output_tokens = None
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=api_messages,
            max_tokens=1024,
            temperature=0.7,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            # OpenAI streaming: chunk.choices[0].delta.content 是增量
            if chunk.choices:
                delta = chunk.choices[0].delta
                token = (delta.content or "") if delta else ""
                if token:
                    full_text_parts.append(token)
                    yield token
            # 最后一个 chunk 通常带 usage(stream_options=include_usage)
            if getattr(chunk, "usage", None):
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        # 把错误也 yield 出去,前端能展示
        yield f"\n\n[Agent 一时回答不了:{error}]"
        raise
    finally:
        # 写 llm_call_log(失败不影响主流程)
        try:
            log = LlmCallLog(
                user_id=conversation.host_user_id,
                role="host_agent",
                provider="dashscope",
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=None,
                error=error,
                related_table="agent_conversations",
                related_id=conversation.id,
            )
            db.add(log)
            await db.commit()
        except Exception as log_err:
            print(f"[agent_self] log write failed: {log_err}")


# ========================================
# 高层封装:用户发消息 → 流回复 → 落库
# ========================================

async def stream_and_persist(
    db: AsyncSession,
    *,
    conversation: AgentConversation,
    user_message_content: str,
) -> AsyncGenerator[str, None]:
    """
    用户消息 → 流式回复的端到端封装。

    顺序:
      1. persist user message
      2. yield tokens (streaming)
      3. persist assistant message + async embed both

    供 router 一行调:
      async for tok in stream_and_persist(...): yield tok
    """
    user_msg = await persist_user_message(
        db, conversation=conversation, content=user_message_content
    )

    full_parts: list[str] = []
    try:
        async for token in stream_agent_reply(
            db,
            conversation=conversation,
            user_message_content=user_message_content,
        ):
            full_parts.append(token)
            yield token
    finally:
        full_text = "".join(full_parts).strip()
        if full_text:
            assistant_msg = await persist_assistant_message(
                db, conversation=conversation, content=full_text
            )
            # embedding 同步生成 — 量小,等一下不影响用户体感(stream 已经结束)
            await embed_message_async(db, message=assistant_msg)
        # user 消息也补 embedding(给后续 RAG 跨会话检索)
        await embed_message_async(db, message=user_msg)
