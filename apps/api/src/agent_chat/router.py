"""
04 · Agent 互聊 · API · 给宿主回看

入口:
- GET /api/agent_chat/me   本人作为 host 出现的所有 agent_chat 场次
                            (用作 "Agent 替我聊过谁" 历史档案)

铁律(对方 private_signals 永不暴露)由 src/summary/router.py:get_agent_chat_for_summary
统一处理;本路由只返回元数据,不返回 messages。
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.deps import CurrentUser
from src.auth.models import User
from src.match.models import Match
from src.shared.db import get_session
from src.summary.models import Summary, SummaryDecision

router = APIRouter()


class AgentChatHistoryItem(BaseModel):
    """Agent 互聊场次摘要 — 列表里给宿主看的卡片数据"""
    model_config = ConfigDict(from_attributes=True)

    agent_chat_id: int
    match_id: int
    peer_user_id: int  # 平台脱敏前的对方 user_id(前端按需展示 user_X)
    status: str
    end_reason: Optional[str] = None
    turns: int  # 该场实际跑了几轮
    started_at: Optional[str] = None  # ISO,前端格式化
    related_summary_id: Optional[int] = None  # 该场关联给当前 host 的 summary
    related_verdict: Optional[str] = None  # "来电" / "不合" / "有点意思再观察" / null
    user_decision: Optional[str] = None  # 当前 host 在那张 summary 上做的决策


@router.get("/me", response_model=list[AgentChatHistoryItem])
async def list_my_agent_chats(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    本人作为 host(match.user_a 或 user_b)出现过的所有 agent_chat。
    包含 re_dispatched 的旧场(用户主动否决,但记录有诊断价值)— 按 started_at desc 排。
    每场附带 host 视角的 summary id + verdict + decision。
    """
    # 1. 拉所有跟当前用户相关的 match 的 agent_chats
    rows = (await db.execute(
        select(AgentChat, Match)
        .join(Match, Match.id == AgentChat.match_id)
        .where(or_(Match.user_a_id == current_user.id, Match.user_b_id == current_user.id))
        .order_by(AgentChat.started_at.desc())
    )).all()

    if not rows:
        return []

    chat_ids = [c.id for c, _ in rows]

    # 2. 一次性拉每场的 turn count
    turn_counts_rows = (await db.execute(
        select(
            AgentChatMessage.agent_chat_id,
            func.count(AgentChatMessage.id).label("turns"),
        )
        .where(AgentChatMessage.agent_chat_id.in_(chat_ids))
        .group_by(AgentChatMessage.agent_chat_id)
    )).all()
    turns_by_chat: dict[int, int] = {r.agent_chat_id: r.turns for r in turn_counts_rows}

    # 3. 一次性拉每场关联的 host summary(summary_type='agent_chat' + host_user_id 当前用户)
    summary_rows = (await db.execute(
        select(Summary).where(
            Summary.agent_chat_id.in_(chat_ids),
            Summary.host_user_id == current_user.id,
            Summary.summary_type == "agent_chat",
        )
    )).scalars().all()
    summary_by_chat: dict[int, Summary] = {s.agent_chat_id: s for s in summary_rows}

    # 4. 拉这些 summary 的 host 决策
    summary_ids = [s.id for s in summary_rows]
    decisions: list[SummaryDecision] = []
    if summary_ids:
        decisions = (await db.execute(
            select(SummaryDecision).where(
                SummaryDecision.summary_id.in_(summary_ids),
                SummaryDecision.user_id == current_user.id,
            )
        )).scalars().all()
    decision_by_summary: dict[int, SummaryDecision] = {d.summary_id: d for d in decisions}

    # 5. 组装
    out: list[AgentChatHistoryItem] = []
    for chat, match in rows:
        peer_id = match.user_b_id if match.user_a_id == current_user.id else match.user_a_id
        sm = summary_by_chat.get(chat.id)
        dec = decision_by_summary.get(sm.id) if sm else None
        out.append(AgentChatHistoryItem(
            agent_chat_id=chat.id,
            match_id=chat.match_id,
            peer_user_id=peer_id,
            status=chat.status,
            end_reason=chat.end_reason,
            turns=turns_by_chat.get(chat.id, 0),
            started_at=chat.started_at.isoformat() if chat.started_at else None,
            related_summary_id=sm.id if sm else None,
            related_verdict=sm.verdict if sm else None,
            user_decision=dec.decision if dec else None,
        ))
    return out
