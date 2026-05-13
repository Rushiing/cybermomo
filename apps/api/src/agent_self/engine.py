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

from src.agent_chat.models import AgentChat
from src.agent_self.models import AgentConversation, AgentConversationMessage
from src.agent_self.prompts import build_system_prompt
from src.agent_self.rag import retrieve_context
from src.auth.models import UserProfile
from src.llm.gateway import _get_client, _model_for_role, llm_embed
from src.llm.models import LlmCallLog
from src.match.models import Match
from src.md.models import MdDocument
from src.shared.db import SessionLocal
from src.shared.peer_prompt import format_peer_block


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


async def _resolve_peer_user_id(
    db: AsyncSession, *, conversation: AgentConversation
) -> Optional[int]:
    """
    根据会话 scope + context_refs 解出当前在聊的"对方 user_id"(没有就 None)。

      - general:没有 peer
      - revisit:context_refs.peer_user_id
      - plaza:context_refs.target_user_id
      - room:context_refs.agent_chat_id → 查 AgentChat → match → 对方 user_id
    """
    refs = conversation.context_refs or {}
    if conversation.scope == "revisit":
        pid = refs.get("peer_user_id")
        return int(pid) if pid else None
    if conversation.scope == "plaza":
        pid = refs.get("target_user_id")
        return int(pid) if pid else None
    if conversation.scope == "room":
        chat_id = refs.get("agent_chat_id")
        if not chat_id:
            return None
        chat = (await db.execute(
            select(AgentChat).where(AgentChat.id == int(chat_id))
        )).scalar_one_or_none()
        if chat is None:
            return None
        match = (await db.execute(
            select(Match).where(Match.id == chat.match_id)
        )).scalar_one_or_none()
        if match is None:
            return None
        return match.user_b_id if match.user_a_id == conversation.host_user_id else match.user_a_id
    return None


async def _load_peer_block(
    db: AsyncSession, *, conversation: AgentConversation
) -> Optional[str]:
    """如果 conversation 关联了具体 peer,返回 peer demographic prompt block"""
    peer_user_id = await _resolve_peer_user_id(db, conversation=conversation)
    if peer_user_id is None:
        return None
    rows = (await db.execute(
        select(UserProfile).where(
            UserProfile.user_id.in_([conversation.host_user_id, peer_user_id])
        )
    )).scalars().all()
    by_uid = {up.user_id: up for up in rows}
    host_up = by_uid.get(conversation.host_user_id)
    peer_up = by_uid.get(peer_user_id)
    return format_peer_block(
        peer_nickname=peer_up.nickname if peer_up else None,
        peer_user_id=peer_user_id,
        peer_age_band=peer_up.age_band if peer_up else None,
        peer_gender=peer_up.gender if peer_up else None,
        peer_mbti=peer_up.mbti if peer_up else None,
        host_age_band=host_up.age_band if host_up else None,
    )


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
    peer_block = await _load_peer_block(db, conversation=conversation)
    system_prompt = build_system_prompt(
        profile_json=profile_json, chunks=chunks, peer_block=peer_block
    )

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
    conversation_id: int,
    host_user_id: int,
    user_message_content: str,
) -> AsyncGenerator[str, None]:
    """
    用户消息 → 流式回复的端到端封装。**关键性能特性**:DB 连接只在 prep/persist
    两个短阶段持有,LLM 流期间(几秒-几十秒)不占连接,避免池子被流式请求拖死。

    阶段:
      1. (短) embed user query(no DB)
      2. (短) Session 1:persist user msg + load profile/history/RAG context
      3. (长) LLM stream(no DB)
      4. (短) Session 2:persist assistant msg + embeds + 更新 conv last_message_at

    出错时(任何 await raise)— generator 的 except 块 yield 错误信息,调用方
    router 用 except 兜底转 SSE 'error' event。
    """
    from datetime import datetime, timezone

    # Phase 1: embed query(off-pool)
    query_vector: Optional[list[float]] = None
    try:
        emb = await llm_embed(user_message_content)
        query_vector = emb.vector
    except Exception as e:
        print(f"[agent_self] query embed failed: {e}")
        # 不致命,RAG 走纯 .md profile 兜底,继续

    # Phase 2: 短 session — 落 user msg + 拉上下文 + 拼 prompt
    async with SessionLocal() as db:
        conv = (
            await db.execute(
                select(AgentConversation).where(AgentConversation.id == conversation_id)
            )
        ).scalar_one_or_none()
        if conv is None or conv.host_user_id != host_user_id:
            raise ValueError("conversation not found or not owned")

        user_msg = await persist_user_message(
            db, conversation=conv, content=user_message_content
        )
        user_msg_id = user_msg.id

        profile_json = await _load_host_profile(db, host_user_id)
        history = await _load_recent_history(db, conversation_id)

        if query_vector is not None:
            chunks = await _retrieve_context_with_vector(
                db,
                user_id=host_user_id,
                query_vector=query_vector,
                exclude_conversation_id=conversation_id,
            )
        else:
            chunks = []

        peer_block = await _load_peer_block(db, conversation=conv)
        system_prompt = build_system_prompt(
            profile_json=profile_json, chunks=chunks, peer_block=peer_block
        )

        api_messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in history:
            if m.role in ("user", "assistant"):
                api_messages.append({"role": m.role, "content": m.content})
    # session 1 释放,DB 连接归还池子

    # Phase 3: LLM 流(无 DB 占用)
    full_parts: list[str] = []
    error: Optional[str] = None
    input_tokens = output_tokens = None
    client = _get_client()
    model = _model_for_role("host_agent")

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
            if chunk.choices:
                delta = chunk.choices[0].delta
                token = (delta.content or "") if delta else ""
                if token:
                    full_parts.append(token)
                    yield token
            if getattr(chunk, "usage", None):
                input_tokens = chunk.usage.prompt_tokens
                output_tokens = chunk.usage.completion_tokens
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        yield f"\n\n[Agent 一时回答不了:{error}]"
    finally:
        full_text = "".join(full_parts).strip()

        # Phase 4: 短 session — 落 assistant msg + embeds + log + last_message_at
        try:
            async with SessionLocal() as db:
                # 写 LLM call log
                db.add(LlmCallLog(
                    user_id=host_user_id,
                    role="host_agent",
                    provider="dashscope",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=None,
                    error=error,
                    related_table="agent_conversations",
                    related_id=conversation_id,
                ))

                # 回填 user msg 的 embedding(query 已经 embed 过了)
                if query_vector is not None:
                    user_row = (
                        await db.execute(
                            select(AgentConversationMessage).where(
                                AgentConversationMessage.id == user_msg_id
                            )
                        )
                    ).scalar_one_or_none()
                    if user_row is not None and user_row.embedding is None:
                        user_row.embedding = query_vector

                # 落 assistant msg(如果生成了文本)+ 嵌入
                if full_text:
                    # 重新查 conv 拿最新 turn 计数
                    conv = (
                        await db.execute(
                            select(AgentConversation).where(
                                AgentConversation.id == conversation_id
                            )
                        )
                    ).scalar_one_or_none()
                    if conv is not None:
                        assistant_msg = await persist_assistant_message(
                            db, conversation=conv, content=full_text
                        )
                        # assistant embed
                        try:
                            emb_resp = await llm_embed(full_text)
                            assistant_msg.embedding = emb_resp.vector
                        except Exception as e:
                            print(f"[agent_self] assistant embed failed: {e}")

                await db.commit()
        except Exception as e:
            print(f"[agent_self] phase 4 persist failed: {e}")


async def _retrieve_context_with_vector(
    db: AsyncSession,
    *,
    user_id: int,
    query_vector: list[float],
    exclude_conversation_id: Optional[int] = None,
    top_k_per_source: int = 3,
):
    """retrieve_context 的变体 — 接受已 embed 过的 vector,省一次 LLM 调用"""
    from src.agent_self.rag import (
        ContextChunk,
        _format_summary_for_rag,
    )
    from src.agent_chat.models import AgentChat
    from src.auth.models import UserProfile
    from src.match.models import Match
    from src.md.models import MdSegment
    from src.summary.models import Summary

    out: list = []
    qv = query_vector

    # md segments
    md_q = (
        select(
            MdSegment.id,
            MdSegment.content,
            MdSegment.segment_type,
            MdSegment.embedding.cosine_distance(qv).label("distance"),
        )
        .where(MdSegment.user_id == user_id)
        .where(MdSegment.embedding.is_not(None))
        .order_by("distance")
        .limit(top_k_per_source)
    )
    for row in (await db.execute(md_q)).all():
        out.append(ContextChunk(
            source="md",
            ref_id=row.id,
            text=row.content,
            distance=float(row.distance),
            metadata={"segment_type": row.segment_type},
        ))

    # summaries + peer nickname
    sm_q = (
        select(
            Summary.id,
            Summary.verdict,
            Summary.summary_type,
            Summary.highlights,
            Summary.risks,
            Summary.recommended_action,
            Summary.embedding.cosine_distance(qv).label("distance"),
            Match.user_a_id,
            Match.user_b_id,
        )
        .outerjoin(AgentChat, AgentChat.id == Summary.agent_chat_id)
        .outerjoin(Match, Match.id == AgentChat.match_id)
        .where(Summary.host_user_id == user_id)
        .where(Summary.embedding.is_not(None))
        .order_by("distance")
        .limit(top_k_per_source)
    )
    sm_rows = (await db.execute(sm_q)).all()
    peer_ids = set()
    for row in sm_rows:
        if row.user_a_id is None or row.user_b_id is None:
            continue
        peer_ids.add(row.user_b_id if row.user_a_id == user_id else row.user_a_id)
    nickname_by_uid: dict[int, str] = {}
    if peer_ids:
        nick_rows = (await db.execute(
            select(UserProfile.user_id, UserProfile.nickname).where(
                UserProfile.user_id.in_(peer_ids)
            )
        )).all()
        nickname_by_uid = {r.user_id: r.nickname for r in nick_rows if r.nickname}
    for row in sm_rows:
        peer_id = None
        if row.user_a_id is not None and row.user_b_id is not None:
            peer_id = row.user_b_id if row.user_a_id == user_id else row.user_a_id
        peer_nickname = nickname_by_uid.get(peer_id) if peer_id else None
        text = _format_summary_for_rag(
            verdict=row.verdict,
            highlights=row.highlights,
            risks=row.risks,
            recommended=row.recommended_action,
            peer_nickname=peer_nickname,
        )
        out.append(ContextChunk(
            source="summary",
            ref_id=row.id,
            text=text,
            distance=float(row.distance),
            metadata={
                "verdict": row.verdict,
                "summary_type": row.summary_type,
                "peer_user_id": peer_id,
                "peer_nickname": peer_nickname,
            },
        ))

    # past conversation messages
    conv_q = (
        select(
            AgentConversationMessage.id,
            AgentConversationMessage.conversation_id,
            AgentConversationMessage.role,
            AgentConversationMessage.content,
            AgentConversationMessage.embedding.cosine_distance(qv).label("distance"),
        )
        .join(
            AgentConversation,
            AgentConversation.id == AgentConversationMessage.conversation_id,
        )
        .where(AgentConversation.host_user_id == user_id)
        .where(AgentConversationMessage.embedding.is_not(None))
        .where(AgentConversationMessage.role != "system")
        .order_by("distance")
        .limit(top_k_per_source)
    )
    if exclude_conversation_id is not None:
        conv_q = conv_q.where(
            AgentConversationMessage.conversation_id != exclude_conversation_id
        )
    for row in (await db.execute(conv_q)).all():
        out.append(ContextChunk(
            source="past_conversation",
            ref_id=row.id,
            text=row.content,
            distance=float(row.distance),
            metadata={"role": row.role, "conversation_id": row.conversation_id},
        ))

    out.sort(key=lambda c: c.distance)
    return out
