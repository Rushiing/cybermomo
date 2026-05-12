"""
05 · 个人房间 · API

聚合视图层(卡片由 matches/summaries/chat_sessions 动态聚合)。
- GET /api/room/status      顶部状态栏("Agent 正在聊 N 个 · 其中 M 个有戏")
- GET /api/room/cards       卡片流(简报卡 + 真人聊天入口卡)
- 软拉黑相关 endpoint:GET / DELETE
"""
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat
from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.match.models import Match, MatchHook
from src.room.models import UserSoftBlocklist
from src.shared.db import SessionLocal, get_session
from src.summary.models import Summary, SummaryDecision

router = APIRouter()


# ========================================
# Schema
# ========================================

class RoomStatusResponse(BaseModel):
    chatting_count: int  # Agent 正在聊几个
    spark_count: int  # 有戏(verdict='来电')几个
    total_summaries_pending: int  # 待决策的简报数


class TopHint(BaseModel):
    nickname: Optional[str] = None
    topic: Optional[str] = None  # 暂时占位


class RoomStatusFullResponse(RoomStatusResponse):
    top_hint: Optional[TopHint] = None  # "其中 @森屿 已经聊到第 4 个话题了"


class SoftBlockEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    blocked_user_id: int
    reason: Optional[str] = None
    created_at: datetime


# ========================================
# 状态栏
# ========================================

@router.get("/status", response_model=RoomStatusFullResponse)
async def get_room_status(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    返回 chatting / spark / pending 计数 + top_hint。

    性能:之前 7 条串行 SQL(SELECT 全部 row 后 len() + 4 个 top_hint join)。
    优化:
      - 计数用 COUNT() 不 fetch row
      - 3 个独立 COUNT 用独立 sessions 并发跑
      - top_hint 一条 JOIN 查 → 总共 3-4 个 round-trip,且大部分并行
    """
    uid = current_user.id

    # 三个 COUNT + 一个 top_hint detail,全部并发
    (
        chatting_count,
        spark_count,
        pending_count,
        top_hint,
    ) = await asyncio.gather(
        _count_chatting(uid),
        _count_spark(uid),
        _count_pending(uid),
        _build_top_hint_single_query(uid),
    )

    return RoomStatusFullResponse(
        chatting_count=chatting_count,
        spark_count=spark_count,
        total_summaries_pending=pending_count,
        top_hint=top_hint,
    )


async def _count_chatting(uid: int) -> int:
    async with SessionLocal() as db:
        return await db.scalar(
            select(func.count())
            .select_from(AgentChat)
            .join(Match, AgentChat.match_id == Match.id)
            .where(
                AgentChat.status == "running",
                or_(Match.user_a_id == uid, Match.user_b_id == uid),
            )
        ) or 0


async def _count_spark(uid: int) -> int:
    async with SessionLocal() as db:
        return await db.scalar(
            select(func.count())
            .select_from(Summary)
            .outerjoin(
                SummaryDecision,
                and_(
                    SummaryDecision.summary_id == Summary.id,
                    SummaryDecision.user_id == uid,
                ),
            )
            .where(
                Summary.host_user_id == uid,
                Summary.verdict == "来电",
                SummaryDecision.id.is_(None),
            )
        ) or 0


async def _count_pending(uid: int) -> int:
    async with SessionLocal() as db:
        return await db.scalar(
            select(func.count())
            .select_from(Summary)
            .outerjoin(
                SummaryDecision,
                and_(
                    SummaryDecision.summary_id == Summary.id,
                    SummaryDecision.user_id == uid,
                ),
            )
            .where(
                Summary.host_user_id == uid,
                SummaryDecision.id.is_(None),
            )
        ) or 0


async def _build_top_hint_single_query(uid: int) -> Optional[TopHint]:
    """
    一条 SQL 拉「最新一条未决策的来电简报」+ 对方 nickname + 第一条 hook_text。
    没有来电的简报就返回 None。
    """
    async with SessionLocal() as db:
        # peer_user_id CASE:Match.user_a 是 host 时 peer = user_b,反之
        # 用 PostgreSQL CASE WHEN
        from sqlalchemy import case, literal

        peer_user_id = case(
            (Match.user_a_id == uid, Match.user_b_id),
            else_=Match.user_a_id,
        ).label("peer_user_id")

        stmt = (
            select(
                Summary.id.label("summary_id"),
                Summary.highlights.label("highlights"),
                peer_user_id,
                Match.id.label("match_id"),
            )
            .join(AgentChat, AgentChat.id == Summary.agent_chat_id)
            .join(Match, Match.id == AgentChat.match_id)
            .outerjoin(
                SummaryDecision,
                and_(
                    SummaryDecision.summary_id == Summary.id,
                    SummaryDecision.user_id == uid,
                ),
            )
            .where(
                Summary.host_user_id == uid,
                Summary.verdict == "来电",
                SummaryDecision.id.is_(None),
            )
            .order_by(Summary.created_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return None

        # 拉对方 nickname + 这次 match 给 host 的第一条 hook,合一个 SQL
        peer_nick_stmt = select(UserProfile.nickname).where(
            UserProfile.user_id == row.peer_user_id
        )
        hook_stmt = (
            select(MatchHook.hook_text)
            .where(
                MatchHook.match_id == row.match_id,
                MatchHook.target_user_id == uid,
            )
            .order_by(MatchHook.id)
            .limit(1)
        )
        # 两个查询小且 PG 缓存友好,串行也快;但并发更好
        peer_nick, hook_text = await asyncio.gather(
            db.scalar(peer_nick_stmt),
            db.scalar(hook_stmt),
        )

        nickname = peer_nick or f"user_{row.peer_user_id}"
        topic: Optional[str] = None
        if hook_text:
            topic = hook_text
        elif row.highlights:
            first = row.highlights[0]
            if isinstance(first, dict) and first.get("text"):
                topic = first["text"][:40]

        return TopHint(nickname=nickname, topic=topic)


# ========================================
# 软拉黑
# ========================================

@router.get("/blocklist", response_model=list[SoftBlockEntry])
async def list_my_blocklist(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    rows = (await db.execute(
        select(UserSoftBlocklist).where(UserSoftBlocklist.user_id == current_user.id)
    )).scalars().all()
    return rows


@router.delete("/blocklist/{blocked_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_blocklist(
    blocked_user_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """解除软拉黑"""
    from sqlalchemy import delete
    await db.execute(
        delete(UserSoftBlocklist).where(
            UserSoftBlocklist.user_id == current_user.id,
            UserSoftBlocklist.blocked_user_id == blocked_user_id,
        )
    )
    await db.commit()
    return None
