"""
06 · Agent 简报 · API

- GET    /api/summary/me              本人收到的简报列表(active 优先)
- GET    /api/summary/{id}            单个简报详情(host scoped)
- POST   /api/summary/{id}/decision   决策(开聊 / 再派 / 丢 / 调方向)
- POST   /api/summary/{id}/redispatch (Phase 4) 同 Agent 换话题再派一次
"""
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
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


# ========================================
# Agent 互聊 messages 查看(给宿主自己看的)
# ========================================

class AgentChatMessageView(BaseModel):
    """暴露给宿主的 Agent 互聊消息(已脱敏)
    - 自己 Agent 说的话:全部 utterance + 自己的 public + private signals
    - 对方 Agent 说的话:utterance + public_signals(intent, topic_ref)
                         · private_signals **不暴露**(铁律)
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    speaker: str  # "host" | "peer"
    turn: int
    topic_ref: str
    intent: str
    utterance: str
    public_signals: dict[str, Any]
    own_private_signals: Optional[dict[str, Any]] = None  # 仅当 speaker=host 时填


class AgentChatViewResponse(BaseModel):
    agent_chat_id: int
    status: str
    end_reason: Optional[str] = None
    turns: int
    messages: list[AgentChatMessageView]


@router.get("/{summary_id}/agent_chat", response_model=AgentChatViewResponse)
async def get_agent_chat_for_summary(
    summary_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    返回该简报对应的 Agent 互聊消息(给宿主看)。
    - 仅 summary.host_user_id == current_user 才能查
    - 对方 Agent 的 private_signals 一律不暴露(铁律)
    - 自己 Agent 的 private_signals 可以看

    用于"看看 Agent 们都聊了什么"入口。
    """
    s = (await db.execute(
        select(Summary).where(
            Summary.id == summary_id,
            Summary.host_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if s is None or s.agent_chat_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="简报不存在或没有关联 Agent 互聊")

    chat = (await db.execute(
        select(AgentChat).where(AgentChat.id == s.agent_chat_id)
    )).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent 互聊不存在")

    msgs = (await db.execute(
        select(AgentChatMessage)
        .where(AgentChatMessage.agent_chat_id == chat.id)
        .order_by(AgentChatMessage.turn)
    )).scalars().all()

    out_msgs = [
        AgentChatMessageView(
            id=m.id,
            speaker="host" if m.speaker_user_id == current_user.id else "peer",
            turn=m.turn,
            topic_ref=m.topic_ref,
            intent=m.intent,
            utterance=m.utterance,
            public_signals=m.public_signals or {},
            own_private_signals=m.private_signals if m.speaker_user_id == current_user.id else None,
        )
        for m in msgs
    ]

    return AgentChatViewResponse(
        agent_chat_id=chat.id,
        status=chat.status,
        end_reason=chat.end_reason,
        turns=len(out_msgs),
        messages=out_msgs,
    )


@router.post("/{summary_id}/decision", response_model=SummaryResponse)
async def make_decision(
    summary_id: int,
    payload: DecisionRequest,
    background_tasks: BackgroundTasks,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    用户在简报卡上的决策。
    - open_human_chat:开真人聊天(等对方也决策)
    - re_dispatch:同 Agent 换话题再派一次(后台 pipeline 跑新一场)
    - drop:丢(软拉黑该用户)
    - chat_with_my_agent:跟自己 Agent 调方向(MVP:仅记录)

    drop 会自动加软拉黑,wildcard 后续会排除。
    re_dispatch 会触发后台任务:同 match 同 Agent 换话题再聊一场,跑完生成新简报。
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

    # re_dispatch:决策提交后,后台跑同 match 的新一场 agent_chat + summary
    if payload.decision == "re_dispatch":
        from src.match.pipeline import run_redispatch_for_summary

        background_tasks.add_task(
            run_redispatch_for_summary,
            summary_id=s.id,
            requester_user_id=current_user.id,
        )

    return _to_response(s, decision)
