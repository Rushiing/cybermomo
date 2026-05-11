"""
05 · 个人房间 · API

聚合视图层(卡片由 matches/summaries/chat_sessions 动态聚合)。
- GET /api/room/status      顶部状态栏("Agent 正在聊 N 个 · 其中 M 个有戏")
- GET /api/room/cards       卡片流(简报卡 + 真人聊天入口卡)
- 软拉黑相关 endpoint:GET / DELETE
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat
from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.match.models import Match, MatchHook
from src.room.models import UserSoftBlocklist
from src.shared.db import get_session
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
    # 正在聊:status='running' 的 agent_chats 中 user 涉及的
    chatting_q = (
        select(AgentChat)
        .join(Match, AgentChat.match_id == Match.id)
        .where(
            AgentChat.status == "running",
            or_(Match.user_a_id == current_user.id, Match.user_b_id == current_user.id),
        )
    )
    chatting = (await db.execute(chatting_q)).scalars().all()

    # 有戏:本人收到的 verdict='来电' summaries(且未决策)
    spark_q = (
        select(Summary)
        .outerjoin(
            SummaryDecision,
            and_(
                SummaryDecision.summary_id == Summary.id,
                SummaryDecision.user_id == current_user.id,
            ),
        )
        .where(
            Summary.host_user_id == current_user.id,
            Summary.verdict == "来电",
            SummaryDecision.id.is_(None),
        )
    )
    spark = (await db.execute(spark_q)).scalars().all()

    # 总待决策数
    pending_q = (
        select(Summary)
        .outerjoin(
            SummaryDecision,
            and_(
                SummaryDecision.summary_id == Summary.id,
                SummaryDecision.user_id == current_user.id,
            ),
        )
        .where(
            Summary.host_user_id == current_user.id,
            SummaryDecision.id.is_(None),
        )
    )
    pending = (await db.execute(pending_q)).scalars().all()

    # top_hint:从有戏的简报里挑最近一张,拉对方 nickname + 第一条 highlight 关键词
    top_hint = await _build_top_hint(db, host_user_id=current_user.id, spark_summaries=spark)

    return RoomStatusFullResponse(
        chatting_count=len(chatting),
        spark_count=len(spark),
        total_summaries_pending=len(pending),
        top_hint=top_hint,
    )


async def _build_top_hint(
    db: AsyncSession,
    *,
    host_user_id: int,
    spark_summaries: list[Summary],
) -> Optional[TopHint]:
    """
    从「有戏」简报里挑最新一张,拉对方 nickname + 一句话钩子。
    没有有戏的就返回 None(状态栏退化成"Agent 正在聊 N 个 · 0 个有戏")。
    """
    if not spark_summaries:
        return None
    # 取最新一张
    sm = max(spark_summaries, key=lambda s: s.created_at)
    if sm.agent_chat_id is None:
        return None

    # 找对方 user_id
    chat = (await db.execute(
        select(AgentChat).where(AgentChat.id == sm.agent_chat_id)
    )).scalar_one_or_none()
    if chat is None:
        return None
    match = (await db.execute(
        select(Match).where(Match.id == chat.match_id)
    )).scalar_one_or_none()
    if match is None:
        return None
    peer_id = match.user_b_id if match.user_a_id == host_user_id else match.user_a_id

    # 对方 nickname
    peer_profile = (await db.execute(
        select(UserProfile).where(UserProfile.user_id == peer_id)
    )).scalar_one_or_none()
    nickname = peer_profile.nickname if peer_profile else f"user_{peer_id}"

    # 钩子:取这次匹配里给宿主看的第一条 hook,fallback 用 summary 第一条 highlight
    topic: Optional[str] = None
    hook = (await db.execute(
        select(MatchHook)
        .where(MatchHook.match_id == match.id, MatchHook.target_user_id == host_user_id)
        .order_by(MatchHook.id)
        .limit(1)
    )).scalar_one_or_none()
    if hook and hook.hook_text:
        topic = hook.hook_text
    elif sm.highlights:
        first = sm.highlights[0]
        if isinstance(first, dict) and first.get("text"):
            # 取前 40 字,避免状态栏被一句完整 highlight 塞满
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
