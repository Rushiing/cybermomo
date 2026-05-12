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
from src.auth.models import User, UserProfile
from src.human_chat.models import ChatSession
from src.match.models import Match
from src.room.models import UserSoftBlocklist
from src.shared.db import get_session
from src.summary.models import Summary, SummaryDecision
from src.summary.schemas import DecisionRequest, SummaryResponse

router = APIRouter()


def _to_response(
    s: Summary,
    decision: Optional[SummaryDecision] = None,
    *,
    peer_user_id: Optional[int] = None,
    peer_nickname: Optional[str] = None,
) -> SummaryResponse:
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
        peer_user_id=peer_user_id,
        peer_nickname=peer_nickname,
    )


async def _load_peer_info_for_summaries(
    db: AsyncSession,
    summaries: list[Summary],
    *,
    host_user_id: int,
) -> dict[int, tuple[Optional[int], Optional[str]]]:
    """
    给一批 summaries 一次性查出每张 → (peer_user_id, peer_nickname)。
    数据流:
      - agent_chat / pre_briefing → agent_chat.match_id → matches.user_a/b
      - human_chat_observation    → chat_sessions.user_a/b
    没关联或对方 user 已删 → 返回 (None, None)
    """
    if not summaries:
        return {}

    agent_chat_ids = {s.agent_chat_id for s in summaries if s.agent_chat_id}
    chat_session_ids = {s.chat_session_id for s in summaries if s.chat_session_id}

    # agent_chat → match
    peer_by_agent_chat: dict[int, int] = {}
    if agent_chat_ids:
        rows = (
            await db.execute(
                select(AgentChat.id, Match.user_a_id, Match.user_b_id)
                .join(Match, Match.id == AgentChat.match_id)
                .where(AgentChat.id.in_(agent_chat_ids))
            )
        ).all()
        for r in rows:
            peer_by_agent_chat[r.id] = (
                r.user_b_id if r.user_a_id == host_user_id else r.user_a_id
            )

    # chat_session 直接拿 user pair
    peer_by_chat_session: dict[int, int] = {}
    if chat_session_ids:
        rows = (
            await db.execute(
                select(
                    ChatSession.id, ChatSession.user_a_id, ChatSession.user_b_id
                ).where(ChatSession.id.in_(chat_session_ids))
            )
        ).all()
        for r in rows:
            peer_by_chat_session[r.id] = (
                r.user_b_id if r.user_a_id == host_user_id else r.user_a_id
            )

    # 收集所有 peer uid 一次性查 nickname
    peer_uid_by_summary: dict[int, int] = {}
    for s in summaries:
        if s.agent_chat_id and s.agent_chat_id in peer_by_agent_chat:
            peer_uid_by_summary[s.id] = peer_by_agent_chat[s.agent_chat_id]
        elif s.chat_session_id and s.chat_session_id in peer_by_chat_session:
            peer_uid_by_summary[s.id] = peer_by_chat_session[s.chat_session_id]

    nickname_by_uid: dict[int, str] = {}
    all_peer_uids = set(peer_uid_by_summary.values())
    if all_peer_uids:
        nick_rows = (
            await db.execute(
                select(UserProfile.user_id, UserProfile.nickname).where(
                    UserProfile.user_id.in_(all_peer_uids)
                )
            )
        ).all()
        nickname_by_uid = {r.user_id: r.nickname for r in nick_rows if r.nickname}

    return {
        sid: (uid, nickname_by_uid.get(uid))
        for sid, uid in peer_uid_by_summary.items()
    }


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

    # 一次性拉所有 summary 对应的对方 nickname(N+1 防御)
    peer_info = await _load_peer_info_for_summaries(
        db, rows_sorted, host_user_id=current_user.id
    )

    return [
        _to_response(
            s,
            decision_by_summary.get(s.id),
            peer_user_id=peer_info.get(s.id, (None, None))[0],
            peer_nickname=peer_info.get(s.id, (None, None))[1],
        )
        for s in rows_sorted
    ]


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

    peer_info = await _load_peer_info_for_summaries(
        db, [s], host_user_id=current_user.id
    )
    peer_uid, peer_nick = peer_info.get(s.id, (None, None))
    return _to_response(s, decision, peer_user_id=peer_uid, peer_nickname=peer_nick)


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

    # chat_with_my_agent:同步种一个 conversation,前端拿到 id 直接跳
    conv_id: Optional[int] = None
    if payload.decision == "chat_with_my_agent":
        from src.agent_self.revisit import seed_room_decision_conversation

        conv_id = await seed_room_decision_conversation(
            db, host_user_id=current_user.id, summary_id=s.id
        )

    peer_info = await _load_peer_info_for_summaries(
        db, [s], host_user_id=current_user.id
    )
    peer_uid, peer_nick = peer_info.get(s.id, (None, None))
    resp = _to_response(
        s, decision, peer_user_id=peer_uid, peer_nickname=peer_nick
    )
    if conv_id is not None:
        resp.agent_conversation_id = conv_id
    return resp
