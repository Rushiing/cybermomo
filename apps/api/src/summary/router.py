"""
06 · Agent 简报 · API

- GET    /api/summary/me              本人收到的简报列表(active 优先)
- GET    /api/summary/{id}            单个简报详情(host scoped)
- POST   /api/summary/{id}/decision   决策(开聊 / 再派 / 丢 / 调方向)
- POST   /api/summary/{id}/redispatch (Phase 4) 同 Agent 换话题再派一次
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import CurrentUser
from src.auth.models import User
from src.match.models import Match
from src.room.models import UserSoftBlocklist
from src.shared.db import get_session
from src.summary.models import Summary, SummaryDecision
from src.summary.schemas import DecisionRequest, SummaryResponse

router = APIRouter()


def _to_response(s: Summary, decision: Optional[SummaryDecision] = None) -> SummaryResponse:
    return SummaryResponse(
        id=s.id,
        agent_chat_id=s.agent_chat_id,
        chat_session_id=s.chat_session_id,
        host_user_id=s.host_user_id,
        summary_type=s.summary_type,
        verdict=s.verdict,
        highlights=s.highlights or [],
        risks=s.risks or [],
        recommended_action=s.recommended_action,
        evidence_chunks=s.evidence_chunks or [],
        created_at=s.created_at,
        user_decision=decision.decision if decision else None,
        decided_at=decision.decided_at if decision else None,
    )


@router.get("/me", response_model=list[SummaryResponse])
async def list_my_summaries(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    本人收到的简报。
    - 来电置顶 + 时间倒序(per 个人房间设计)
    - 同时 join 用户决策记录(已决策的卡片仍展示,用于历史抽屉)
    """
    rows = (await db.execute(
        select(Summary).where(Summary.host_user_id == current_user.id)
    )).scalars().all()

    if not rows:
        return []

    # 拉决策
    summary_ids = [s.id for s in rows]
    decisions = (await db.execute(
        select(SummaryDecision).where(
            SummaryDecision.summary_id.in_(summary_ids),
            SummaryDecision.user_id == current_user.id,
        )
    )).scalars().all()
    decision_by_summary: dict[int, SummaryDecision] = {d.summary_id: d for d in decisions}

    # 排序:来电置顶 + created_at desc;已决策的沉到底部
    def sort_key(s: Summary):
        decided = s.id in decision_by_summary
        verdict_rank = 0 if s.verdict == "来电" else 1 if s.verdict == "有点意思再观察" else 2
        return (decided, verdict_rank, -s.created_at.timestamp())

    rows_sorted = sorted(rows, key=sort_key)
    return [_to_response(s, decision_by_summary.get(s.id)) for s in rows_sorted]


@router.get("/{summary_id}", response_model=SummaryResponse)
async def get_summary(
    summary_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """单条简报。host scope check 由 query 包含"""
    s = (await db.execute(
        select(Summary).where(
            Summary.id == summary_id,
            Summary.host_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="简报不存在或不属于你")

    decision = (await db.execute(
        select(SummaryDecision).where(
            SummaryDecision.summary_id == s.id,
            SummaryDecision.user_id == current_user.id,
        )
    )).scalar_one_or_none()

    return _to_response(s, decision)


@router.post("/{summary_id}/decision", response_model=SummaryResponse)
async def make_decision(
    summary_id: int,
    payload: DecisionRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    用户在简报卡上的决策。
    - open_human_chat:开真人聊天(等对方也决策)
    - re_dispatch:同 Agent 换话题再派一次
    - drop:丢(软拉黑该用户)
    - chat_with_my_agent:跟自己 Agent 调方向

    MVP 阶段 re_dispatch / chat_with_my_agent 不做下游动作(只记录决策);
    drop 会自动加软拉黑,wildcard 后续会排除。
    """
    s = (await db.execute(
        select(Summary).where(
            Summary.id == summary_id,
            Summary.host_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="简报不存在或不属于你")

    # 已决策不可改(MVP 决策不可撤)
    existing = (await db.execute(
        select(SummaryDecision).where(
            SummaryDecision.summary_id == s.id,
            SummaryDecision.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"已经决策过 ({existing.decision}) — MVP 阶段不可撤回",
        )

    decision = SummaryDecision(
        summary_id=s.id,
        user_id=current_user.id,
        decision=payload.decision,
    )
    db.add(decision)

    # 如果是 drop,自动加软拉黑(对方 = match 中的另一方)
    if payload.decision == "drop" and s.agent_chat_id is not None:
        # 找 match
        from src.agent_chat.models import AgentChat

        chat = (await db.execute(
            select(AgentChat).where(AgentChat.id == s.agent_chat_id)
        )).scalar_one_or_none()
        if chat:
            match = (await db.execute(
                select(Match).where(Match.id == chat.match_id)
            )).scalar_one_or_none()
            if match:
                other_user_id = (
                    match.user_b_id if match.user_a_id == current_user.id else match.user_a_id
                )
                # upsert soft blocklist
                exists_block = (await db.execute(
                    select(UserSoftBlocklist).where(
                        UserSoftBlocklist.user_id == current_user.id,
                        UserSoftBlocklist.blocked_user_id == other_user_id,
                    )
                )).scalar_one_or_none()
                if exists_block is None:
                    db.add(UserSoftBlocklist(
                        user_id=current_user.id,
                        blocked_user_id=other_user_id,
                        reason="dropped from summary card",
                    ))

    await db.commit()
    await db.refresh(decision)

    return _to_response(s, decision)
