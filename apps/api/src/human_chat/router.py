"""
07 · 真人聊天室 · API router

- POST /api/chat/sessions/from-summary/{summary_id}    创建 session(双方都 open_human_chat 后)
- GET  /api/chat/sessions/me                          本人涉及的 session 列表
- GET  /api/chat/sessions/{id}                        session 详情
- GET  /api/chat/sessions/{id}/briefing               §4.9 真人聊前简报(LLM 生成 / 取缓存)
- GET  /api/chat/sessions/{id}/messages               消息列表
- POST /api/chat/sessions/{id}/messages               发消息
- POST /api/chat/sessions/{id}/callout                callout(host 私有)
- GET  /api/chat/sessions/{id}/callouts               callout 历史
- POST /api/chat/sessions/{id}/exit                   退出 / 拉黑 / 举报(同时触发观察报告)
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat
from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.human_chat.callout import run_callout
from src.human_chat.models import ChatCallout, ChatMessage, ChatReport, ChatSession
from src.human_chat.observation import run_observation_for_session
from src.human_chat.prebriefing import get_or_create_prebriefing
from src.human_chat.schemas import (
    CalloutRequest,
    CalloutResponse,
    ChatBriefingResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    ExitRequest,
    SendMessageRequest,
)
from src.match.models import Match
from src.room.models import UserSoftBlocklist
from src.shared.db import SessionLocal, get_session
from src.summary.models import Summary, SummaryDecision

router = APIRouter()


def _ensure_participant(session: ChatSession, user_id: int) -> None:
    if user_id not in (session.user_a_id, session.user_b_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="该 session 不属于你"
        )


async def _session_to_response(
    session: ChatSession, *, nickname_by_uid: dict[int, str] | None = None
) -> ChatSessionResponse:
    """ChatSession ORM → API 响应,带双方 nickname"""
    nickname_by_uid = nickname_by_uid or {}
    return ChatSessionResponse(
        id=session.id,
        match_id=session.match_id,
        source_summary_id=session.source_summary_id,
        user_a_id=session.user_a_id,
        user_b_id=session.user_b_id,
        user_a_nickname=nickname_by_uid.get(session.user_a_id),
        user_b_nickname=nickname_by_uid.get(session.user_b_id),
        status=session.status,
        last_message_at=session.last_message_at,
        created_at=session.created_at,
    )


async def _load_nicknames(db: AsyncSession, user_ids: list[int]) -> dict[int, str]:
    """一次性拉一批 user_id 的 nickname"""
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(UserProfile.user_id, UserProfile.nickname).where(
                UserProfile.user_id.in_(set(user_ids))
            )
        )
    ).all()
    return {r.user_id: r.nickname for r in rows if r.nickname}


# ========================================
# Session 创建(双方决定开聊后)
# ========================================

@router.post("/sessions/from-summary/{summary_id}", response_model=ChatSessionResponse)
async def create_session_from_summary(
    summary_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    确认双方都 open_human_chat 后创建 chat_session。
    - 校验:summary 属于 current_user;agent_chat 存在
    - 校验:双方都有 decision='open_human_chat'
    - 已存在则返回现有 session(幂等)
    """
    summary = (await db.execute(
        select(Summary).where(
            Summary.id == summary_id,
            Summary.host_user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if summary is None or summary.agent_chat_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="简报不存在或不属于你")

    chat = (await db.execute(
        select(AgentChat).where(AgentChat.id == summary.agent_chat_id)
    )).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Agent 互聊不存在")

    match = (await db.execute(
        select(Match).where(Match.id == chat.match_id)
    )).scalar_one_or_none()
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="match 不存在")

    # 已有 session 则返回 — 同时若 source_summary_id 还没填(旧记录),回填一下
    existing = (await db.execute(
        select(ChatSession).where(ChatSession.match_id == match.id)
    )).scalar_one_or_none()
    if existing is not None:
        if existing.source_summary_id is None:
            existing.source_summary_id = summary.id
            await db.commit()
            await db.refresh(existing)
        nicks = await _load_nicknames(db, [existing.user_a_id, existing.user_b_id])
        return await _session_to_response(existing, nickname_by_uid=nicks)

    # 校验双方 open_human_chat decision
    decisions = (await db.execute(
        select(SummaryDecision)
        .join(Summary, Summary.id == SummaryDecision.summary_id)
        .where(
            Summary.agent_chat_id == chat.id,
            Summary.summary_type == "agent_chat",
            SummaryDecision.decision == "open_human_chat",
        )
    )).scalars().all()
    decided_user_ids = {d.user_id for d in decisions}
    if {match.user_a_id, match.user_b_id} - decided_user_ids:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="对方还没决定开聊,等等",
        )

    # 创建 session(强制小 id 在前)
    a, b = sorted([match.user_a_id, match.user_b_id])
    session = ChatSession(
        match_id=match.id,
        source_summary_id=summary.id,  # 标记衍生来源
        user_a_id=a,
        user_b_id=b,
        status="active",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    nicks = await _load_nicknames(db, [a, b])
    return await _session_to_response(session, nickname_by_uid=nicks)


# ========================================
# Session 列表 + 详情
# ========================================

@router.get("/sessions/me", response_model=list[ChatSessionResponse])
async def list_my_sessions(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    rows = (await db.execute(
        select(ChatSession).where(
            or_(
                ChatSession.user_a_id == current_user.id,
                ChatSession.user_b_id == current_user.id,
            )
        ).order_by(ChatSession.created_at.desc())
    )).scalars().all()
    uids: list[int] = []
    for s in rows:
        uids.extend([s.user_a_id, s.user_b_id])
    nicks = await _load_nicknames(db, uids)
    return [await _session_to_response(s, nickname_by_uid=nicks) for s in rows]


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session_detail(
    session_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)
    nicks = await _load_nicknames(db, [session.user_a_id, session.user_b_id])
    return await _session_to_response(session, nickname_by_uid=nicks)


# ========================================
# §4.9 真人聊前简报
# ========================================

@router.get("/sessions/{session_id}/briefing", response_model=ChatBriefingResponse)
async def get_briefing(
    session_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)

    # 找对应 agent_chat
    chat = (await db.execute(
        select(AgentChat).where(AgentChat.match_id == session.match_id)
    )).scalar_one_or_none()
    if chat is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="找不到对应的 agent_chat",
        )

    summary = await get_or_create_prebriefing(
        db, agent_chat_id=chat.id, host_user_id=current_user.id
    )
    return ChatBriefingResponse(
        summary_id=summary.id,
        verdict=summary.verdict,
        highlights=summary.highlights or [],
        risks=summary.risks or [],
        recommended_action=summary.recommended_action,
        evidence_chunks=summary.evidence_chunks or [],
        created_at=summary.created_at,
    )


# ========================================
# 消息
# ========================================

@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def list_messages(
    session_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)

    rows = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.sent_at)
    )).scalars().all()
    return rows


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    session_id: int,
    payload: SendMessageRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)
    if session.status != "active":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="session 已结束")

    msg = ChatMessage(
        session_id=session_id,
        sender_user_id=current_user.id,
        content_type=payload.content_type,
        content=payload.content,
    )
    db.add(msg)
    session.last_message_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(msg)
    return msg


# ========================================
# Callout
# ========================================

@router.post(
    "/sessions/{session_id}/callout",
    response_model=CalloutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def make_callout(
    session_id: int,
    payload: CalloutRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)

    callout = await run_callout(
        db,
        session=session,
        host_user_id=current_user.id,
        callout_prompt=payload.callout_prompt,
        context_message_ids=payload.context_message_ids,
    )
    return callout


@router.get("/sessions/{session_id}/callouts", response_model=list[CalloutResponse])
async def list_my_callouts(
    session_id: int,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """**只**返回 current_user 自己的 callout(host 私有)"""
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)

    rows = (await db.execute(
        select(ChatCallout)
        .where(
            ChatCallout.session_id == session_id,
            ChatCallout.host_user_id == current_user.id,  # 铁律 — host scope
        )
        .order_by(ChatCallout.created_at)
    )).scalars().all()
    return rows


# ========================================
# 退出 / 拉黑 / 举报
# ========================================

async def _trigger_observation_async(session_id: int, host_user_id: int) -> None:
    """BackgroundTask:跑观察报告"""
    async with SessionLocal() as db:
        session = (await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )).scalar_one_or_none()
        if session is None:
            return
        try:
            await run_observation_for_session(
                db, session=session, host_user_id=host_user_id
            )
        except Exception as e:
            print(f"[observation] failed session={session_id} host={host_user_id}: {e}")


async def _trigger_agent_revisit_async(
    session_id: int, host_user_id: int, exit_action: str
) -> None:
    """BackgroundTask:种 Agent 回访 conversation"""
    from src.agent_self.revisit import seed_revisit_after_chat_exit
    await seed_revisit_after_chat_exit(session_id, host_user_id, exit_action)


@router.post("/sessions/{session_id}/exit", response_model=ChatSessionResponse)
async def exit_session(
    session_id: int,
    payload: ExitRequest,
    background_tasks: BackgroundTasks,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    主动退出 / 拉黑 / 举报。
    - quit:status='ended_quit',对方仍可重进
    - block:status='ended_block',加软拉黑(双方),session 结束
    - report:status='ended_report',加 chat_reports + 软拉黑

    退出后异步触发**双方**的观察报告(每位 host 一份)。
    """
    session = (await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _ensure_participant(session, current_user.id)

    if session.status != "active":
        return session

    other_user_id = (
        session.user_b_id if session.user_a_id == current_user.id else session.user_a_id
    )

    if payload.action == "quit":
        session.status = "ended_quit"
    elif payload.action == "block":
        session.status = "ended_block"
        # 加软拉黑(单向:current_user 软拉黑 other)
        existing = (await db.execute(
            select(UserSoftBlocklist).where(
                UserSoftBlocklist.user_id == current_user.id,
                UserSoftBlocklist.blocked_user_id == other_user_id,
            )
        )).scalar_one_or_none()
        if existing is None:
            db.add(UserSoftBlocklist(
                user_id=current_user.id,
                blocked_user_id=other_user_id,
                reason="blocked from chat session",
            ))
    elif payload.action == "report":
        session.status = "ended_report"
        db.add(ChatReport(
            session_id=session.id,
            reporter_user_id=current_user.id,
            reported_user_id=other_user_id,
            content=payload.note,
            status="pending",
        ))
        # 举报同时加软拉黑
        existing = (await db.execute(
            select(UserSoftBlocklist).where(
                UserSoftBlocklist.user_id == current_user.id,
                UserSoftBlocklist.blocked_user_id == other_user_id,
            )
        )).scalar_one_or_none()
        if existing is None:
            db.add(UserSoftBlocklist(
                user_id=current_user.id,
                blocked_user_id=other_user_id,
                reason="reported",
            ))

    session.exit_action = payload.action
    session.exit_action_by = current_user.id
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)

    # 异步给双方各跑一份观察报告 + Agent 主动回访
    for host_uid in [session.user_a_id, session.user_b_id]:
        background_tasks.add_task(_trigger_observation_async, session.id, host_uid)
        background_tasks.add_task(
            _trigger_agent_revisit_async, session.id, host_uid, payload.action
        )

    nicks = await _load_nicknames(db, [session.user_a_id, session.user_b_id])
    return await _session_to_response(session, nickname_by_uid=nicks)
