"""
08 · Agent 主动起头的回访 / 决策对话

三个触发场景:
1. 真人聊天 exit (quit / block / report)         → seed_revisit_after_chat_exit
2. 24h 沉默 sweep 自动结束 session                → seed_revisit_after_silent_sweep
3. 简报上点「跟我 Agent 聊聊调方向」              → seed_room_decision_conversation

每个函数都新建一个 AgentConversation,种第一条 assistant 消息(开场白),
让用户下次打开 /me/agent 或浮动 widget 就看到 Agent 主动起头。

注意:开场白是固定模板 — Agent **不调 LLM**,直接由 prompts.revisit_opener /
prompts.room_decision_opener 生成。用户回复后才走 stream_and_persist()。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_self.engine import (
    embed_message_async,
    get_or_create_conversation,
    persist_assistant_message,
)
from src.agent_self.prompts import revisit_opener, room_decision_opener
from src.agent_self.models import AgentConversation
from src.auth.models import UserProfile
from src.human_chat.models import ChatSession
from src.shared.db import SessionLocal
from src.summary.models import Summary


async def _has_revisit_for_session(
    db: AsyncSession, *, host_user_id: int, session_id: int
) -> bool:
    """同一个 session 已经种过 revisit conversation 就不重复种(幂等)"""
    # context_refs 是 JSONB,用 PG 的 ->> 操作符;SQLAlchemy 用 .op('->>')
    stmt = select(AgentConversation).where(
        AgentConversation.host_user_id == host_user_id,
        AgentConversation.scope == "revisit",
        AgentConversation.context_refs.op("->>")("chat_session_id")
        == str(session_id),
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    return existing is not None


async def _has_room_chat_for_summary(
    db: AsyncSession, *, host_user_id: int, summary_id: int
) -> bool:
    stmt = select(AgentConversation).where(
        AgentConversation.host_user_id == host_user_id,
        AgentConversation.scope == "room",
        AgentConversation.context_refs.op("->>")("summary_id")
        == str(summary_id),
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    return existing is not None


# ========================================
# 1. 真人聊天 exit / 沉默 sweep 后回访
# ========================================

async def seed_revisit_after_chat_exit(
    session_id: int, host_user_id: int, exit_action: str
) -> Optional[int]:
    """
    BackgroundTask 入口:在 ChatSession exit/silent 后种一条回访 conversation。

    exit_action ∈ {'quit', 'block', 'report', 'silent'}

    返回新建的 conversation_id;已存在则返回现有 id;失败返回 None。
    """
    try:
        async with SessionLocal() as db:
            # 拉 session 拿到对方 user_id(脱敏在 opener 里用 @user_{peer_id})
            session = (
                await db.execute(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
            ).scalar_one_or_none()
            if session is None:
                print(f"[revisit] session {session_id} not found")
                return None

            # 幂等
            if await _has_revisit_for_session(
                db, host_user_id=host_user_id, session_id=session_id
            ):
                print(f"[revisit] already seeded session={session_id} host={host_user_id}")
                return None

            peer_user_id = (
                session.user_b_id if session.user_a_id == host_user_id
                else session.user_a_id
            )

            # 拉对方 nickname,标题和开场白都用它(脱敏 user_X 是给系统看的,
            # 跟宿主交底时用 nickname 才自然)
            peer_profile = (
                await db.execute(
                    select(UserProfile).where(UserProfile.user_id == peer_user_id)
                )
            ).scalar_one_or_none()
            peer_nickname = peer_profile.nickname if peer_profile else None
            display_peer = peer_nickname or f"user_{peer_user_id}"

            conv = await get_or_create_conversation(
                db,
                host_user_id=host_user_id,
                conversation_id=None,
                scope="revisit",
                title=f"跟 @{display_peer} 聊完之后",
                context_refs={
                    "chat_session_id": session_id,
                    "peer_user_id": peer_user_id,
                    "peer_nickname": peer_nickname,
                    "exit_action": exit_action,
                },
            )

            opener = revisit_opener(
                exit_action=exit_action,
                peer_nickname=peer_nickname,
                peer_user_id=peer_user_id,
            )
            msg = await persist_assistant_message(
                db, conversation=conv, content=opener
            )
            # 开场白也 embed,后续 RAG 可检索
            await embed_message_async(db, message=msg)

            return conv.id
    except Exception as e:
        print(f"[revisit] seed failed session={session_id} host={host_user_id}: {e}")
        return None


# ========================================
# 2. 24h 沉默 sweep(复用上面的 seed,exit_action='silent')
# ========================================

async def seed_revisit_after_silent_sweep(
    session_id: int, host_user_id: int
) -> Optional[int]:
    return await seed_revisit_after_chat_exit(
        session_id, host_user_id, exit_action="silent"
    )


# ========================================
# 3. 简报「跟我 Agent 聊聊」
# ========================================

async def seed_room_decision_conversation(
    db: AsyncSession, *, host_user_id: int, summary_id: int
) -> Optional[int]:
    """
    同步入口:用户在简报上点「跟我 Agent 聊聊」时,decision endpoint 直接调,
    返回 conv_id 让前端跳转。

    幂等:同一 (host, summary) 已种过 conversation 时返回现有 id。
    title / context_refs 锚定在对方 nickname 上(IA 改:第一梯队是 peer)。
    """
    try:
        summary = (
            await db.execute(
                select(Summary).where(
                    Summary.id == summary_id,
                    Summary.host_user_id == host_user_id,
                )
            )
        ).scalar_one_or_none()
        if summary is None:
            print(f"[room_chat] summary {summary_id} not found / not yours")
            return None

        # 幂等
        existing = (
            await db.execute(
                select(AgentConversation).where(
                    AgentConversation.host_user_id == host_user_id,
                    AgentConversation.scope == "room",
                    AgentConversation.context_refs.op("->>")("summary_id")
                    == str(summary_id),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.id

        # 拉对方 user + nickname(顺 agent_chat → match → user_profiles)
        peer_user_id: Optional[int] = None
        peer_nickname: Optional[str] = None
        if summary.agent_chat_id is not None:
            from src.agent_chat.models import AgentChat
            from src.auth.models import UserProfile
            from src.match.models import Match

            row = (
                await db.execute(
                    select(Match.user_a_id, Match.user_b_id)
                    .join(AgentChat, AgentChat.match_id == Match.id)
                    .where(AgentChat.id == summary.agent_chat_id)
                )
            ).first()
            if row is not None:
                peer_user_id = (
                    row.user_b_id if row.user_a_id == host_user_id else row.user_a_id
                )
                nick_row = (
                    await db.execute(
                        select(UserProfile.nickname).where(
                            UserProfile.user_id == peer_user_id
                        )
                    )
                ).scalar_one_or_none()
                peer_nickname = nick_row

        display_peer = peer_nickname or (
            f"user_{peer_user_id}" if peer_user_id else "对方"
        )
        # 第一梯队 IA:title 锚 nickname,verdict 是状态副信息
        title = f"和 @{display_peer} · {summary.verdict}"

        conv = await get_or_create_conversation(
            db,
            host_user_id=host_user_id,
            conversation_id=None,
            scope="room",
            title=title,
            context_refs={
                "summary_id": summary_id,
                "agent_chat_id": summary.agent_chat_id,
                "verdict": summary.verdict,
                "peer_user_id": peer_user_id,
                "peer_nickname": peer_nickname,
            },
        )
        opener = room_decision_opener(
            verdict=summary.verdict, peer_nickname=peer_nickname
        )
        msg = await persist_assistant_message(
            db, conversation=conv, content=opener
        )
        await embed_message_async(db, message=msg)
        return conv.id
    except Exception as e:
        print(f"[room_chat] seed failed summary={summary_id} host={host_user_id}: {e}")
        return None
