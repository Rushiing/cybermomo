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

    性能:全部在**注入的 db 上**串行跑(同一连接),避免一次请求抢多个连接打爆 pool。
    - 3 个 COUNT()(不 fetch 数据)
    - top_hint 用一条 JOIN 拿 summary + match + peer_id,再补 nickname / hook
    """
    uid = current_user.id

    chatting_count = await db.scalar(
        select(func.count())
        .select_from(AgentChat)
        .join(Match, AgentChat.match_id == Match.id)
        .where(
            AgentChat.status == "running",
            or_(Match.user_a_id == uid, Match.user_b_id == uid),
        )
    ) or 0

    spark_count = await db.scalar(
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

    pending_count = await db.scalar(
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

    top_hint = await _build_top_hint(db, host_user_id=uid)

    return RoomStatusFullResponse(
        chatting_count=chatting_count,
        spark_count=spark_count,
        total_summaries_pending=pending_count,
        top_hint=top_hint,
    )


async def _build_top_hint(db: AsyncSession, *, host_user_id: int) -> Optional[TopHint]:
    """
    一条 JOIN SQL 拿到最新一条未决策的「来电」简报关键字段 + peer_id,
    再(同 session 串行)拉 peer nickname 和第一条 hook。
    没有来电就返 None。
    """
    from sqlalchemy import case

    peer_user_id = case(
        (Match.user_a_id == host_user_id, Match.user_b_id),
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
                SummaryDecision.user_id == host_user_id,
            ),
        )
        .where(
            Summary.host_user_id == host_user_id,
            Summary.verdict == "来电",
            SummaryDecision.id.is_(None),
        )
        .order_by(Summary.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None

    peer_nick = await db.scalar(
        select(UserProfile.nickname).where(UserProfile.user_id == row.peer_user_id)
    )
    hook_text = await db.scalar(
        select(MatchHook.hook_text)
        .where(
            MatchHook.match_id == row.match_id,
            MatchHook.target_user_id == host_user_id,
        )
        .order_by(MatchHook.id)
        .limit(1)
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
