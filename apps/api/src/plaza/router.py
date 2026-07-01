"""
08 · 广场 · API

第一版目标:
- GET /api/plaza/feed:用公开字段拼一个可视化广场 feed
- POST /api/plaza/initiate:从社交名片真实发起一次 Agent 试探

边界:
- 不暴露 profile_json / portrait.body / boundary 数值
- 不新增表,主动发起复用 matches → matchpoints → hooks → agent_chat → summaries
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.human_chat.models import ChatSession
from src.match.desensitize import run_desensitize_for_match
from src.match.engine import MatchpointDraft, compute_match
from src.match.models import Match, MatchHook, Matchpoint
from src.md.models import MdDocument
from src.room.models import UserSoftBlocklist
from src.shared.db import SessionLocal, get_session
from src.summary.engine import run_summary_for_chat
from src.summary.models import Summary

router = APIRouter()


class PlazaNode(BaseModel):
    user_id: int
    nickname: str
    age_band: Optional[str] = None
    gender: Optional[str] = None
    mbti: Optional[str] = None
    domains: list[str] = []
    hooks: list[str] = []
    connection_label: Optional[str] = None
    is_self: bool = False
    featured: bool = False
    state: Literal["self", "wander", "shallow_probe", "deep_chat", "human_chat"]
    x: float
    y: float


class PlazaLink(BaseModel):
    source_user_id: int
    target_user_id: int
    kind: Literal["shallow_probe", "deep_chat", "human_chat"]


class PlazaFeedResponse(BaseModel):
    nodes: list[PlazaNode]
    links: list[PlazaLink]
    refreshed_at: datetime


class PlazaInitiateRequest(BaseModel):
    target_user_id: int


class PlazaInitiateResponse(BaseModel):
    status: Literal["queued", "already_running", "already_done"]
    match_id: int
    summary_id: Optional[int] = None
    message: str


@router.get("/feed", response_model=PlazaFeedResponse)
async def get_plaza_feed(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    返回广场公开 feed。

    只使用 L0 公开字段:
    - user_profiles.nickname / age_band / gender / mbti
    - md_documents.domains_interested
    - profile_json.relationship_warmth.connection_value.label
    """
    blocked = await _soft_blocked_ids(db, current_user.id)
    conditions = [
        MdDocument.is_active.is_(True),
        User.deleted_at.is_(None),
    ]
    if blocked:
        conditions.append(MdDocument.user_id.notin_(blocked))

    rows = (await db.execute(
        select(MdDocument, User, UserProfile)
        .join(User, User.id == MdDocument.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == MdDocument.user_id)
        .where(*conditions)
        .order_by(
            (MdDocument.user_id == current_user.id).desc(),
            User.is_system_mock.desc(),
            MdDocument.created_at.desc(),
        )
        .limit(24)
    )).all()

    node_ids = [md.user_id for md, _, _ in rows]
    link_kind_by_pair = await _plaza_links(db, node_ids)

    nodes: list[PlazaNode] = []
    for idx, (md, _, profile) in enumerate(rows):
        state: Literal["self", "wander", "shallow_probe", "deep_chat", "human_chat"] = "wander"
        if md.user_id == current_user.id:
            state = "self"
        else:
            for pair, kind in link_kind_by_pair.items():
                if md.user_id in pair:
                    state = kind
                    break

        connection_label = _connection_label(md.profile_json)
        domains = list(md.domains_interested or [])[:5]
        nodes.append(PlazaNode(
            user_id=md.user_id,
            nickname=(profile.nickname if profile and profile.nickname else "这位用户"),
            age_band=profile.age_band if profile else None,
            gender=profile.gender if profile else None,
            mbti=profile.mbti if profile else None,
            domains=domains,
            hooks=_public_hooks(domains, connection_label),
            connection_label=connection_label,
            is_self=md.user_id == current_user.id,
            featured=(md.user_id == current_user.id or idx < 5),
            state=state,
            x=_stable_coord(md.user_id, "x"),
            y=_stable_coord(md.user_id, "y"),
        ))

    links = [
        PlazaLink(source_user_id=a, target_user_id=b, kind=kind)
        for (a, b), kind in link_kind_by_pair.items()
    ]
    return PlazaFeedResponse(nodes=nodes, links=links, refreshed_at=datetime.now(timezone.utc))


@router.post("/initiate", response_model=PlazaInitiateResponse)
async def initiate_plaza_probe(
    payload: PlazaInitiateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    从广场真实派出 Agent。

    第一版复用深度互聊管线,但入口语义是"广场主动试探"。成功后不在广场等,
    结果回到个人房间的 summary 卡。
    """
    target_user_id = payload.target_user_id
    if target_user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能派 Agent 去试探自己")

    target = await db.scalar(
        select(User).where(User.id == target_user_id, User.deleted_at.is_(None))
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="这位最近不在广场了")

    blocked = await _soft_blocked_ids(db, current_user.id)
    if target_user_id in blocked:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="这位最近不太方便,换个试试?",
        )

    pair = _ordered_pair(current_user.id, target_user_id)
    existing = await db.scalar(
        select(Match).where(Match.user_a_id == pair[0], Match.user_b_id == pair[1])
    )
    if existing is not None:
        response = await _existing_match_response(db, existing, current_user.id)
        if response:
            return response
        existing.status = "agent_chat_running"
        await db.commit()
        background_tasks.add_task(_run_plaza_probe_for_match, existing.id)
        return PlazaInitiateResponse(
            status="queued",
            match_id=existing.id,
            message="我已经派你的 Agent 去试探了。聊完会回到个人房间跟你交底。",
        )

    profiles = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id.in_([current_user.id, target_user_id]),
            MdDocument.is_active.is_(True),
        )
    )).scalars().all()
    profile_by_user = {p.user_id: p for p in profiles}
    if current_user.id not in profile_by_user:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="你还没有 .md,先做完问卷再来广场。")
    if target_user_id not in profile_by_user:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="这位还没准备好被 Agent 试探。")

    a_id, b_id = pair
    score = compute_match(
        profile_by_user[a_id].profile_json,
        profile_by_user[b_id].profile_json,
    )
    match = Match(
        user_a_id=a_id,
        user_b_id=b_id,
        overall_score=score.overall_score,
        is_wildcard=score.overall_score < 0.4,
        status="agent_chat_running",
    )
    db.add(match)
    try:
        await db.flush()
        drafts = score.matchpoints or [
            _fallback_matchpoint(profile_by_user[a_id], profile_by_user[b_id])
        ]
        for draft in drafts[:8]:
            db.add(_make_matchpoint(match.id, draft))
        await db.commit()
        await db.refresh(match)
    except IntegrityError:
        await db.rollback()
        match = await db.scalar(
            select(Match).where(Match.user_a_id == a_id, Match.user_b_id == b_id)
        )
        if match is None:
            raise
        response = await _existing_match_response(db, match, current_user.id)
        if response:
            return response
        match.status = "agent_chat_running"
        await db.commit()

    background_tasks.add_task(_run_plaza_probe_for_match, match.id)
    return PlazaInitiateResponse(
        status="queued",
        match_id=match.id,
        message="我已经派你的 Agent 去试探了。聊完会回到个人房间跟你交底。",
    )


async def _run_plaza_probe_for_match(match_id: int) -> None:
    """后台跑广场主动试探链路。单步失败只打日志,后续 repair 可补。"""
    chat_id: int | None = None

    async with SessionLocal() as db:
        match = await db.scalar(select(Match).where(Match.id == match_id))
        if match is None:
            return
        hook_count = await db.scalar(
            select(func.count()).select_from(MatchHook).where(MatchHook.match_id == match_id)
        ) or 0
        if hook_count == 0:
            try:
                hooks = await run_desensitize_for_match(db, match=match)
            except Exception as e:
                print(f"[plaza] desensitize failed match_id={match_id}: {e}")
                match.status = "pending"
                await db.commit()
                return
            if not hooks:
                print(f"[plaza] desensitize produced no hooks match_id={match_id}")
                match.status = "pending"
                await db.commit()
                return

    async with SessionLocal() as db:
        match = await db.scalar(select(Match).where(Match.id == match_id))
        if match is None:
            return
        running = await db.scalar(
            select(func.count()).select_from(AgentChat).where(
                AgentChat.match_id == match_id,
                AgentChat.status == "running",
            )
        ) or 0
        if running:
            return
        try:
            chat = await run_agent_chat(db, match=match, max_turns=6)
            chat_id = chat.id
            match.status = (
                "agent_chat_done" if "done" in (chat.status or "") else "agent_chat_running"
            )
            await db.commit()
        except Exception as e:
            print(f"[plaza] agent_chat failed match_id={match_id}: {e}")
            match.status = "pending"
            await db.commit()
            return

    if chat_id is None:
        return

    async with SessionLocal() as db:
        chat = await db.scalar(select(AgentChat).where(AgentChat.id == chat_id))
        if chat is None:
            return
        msg_count = await db.scalar(
            select(func.count()).select_from(AgentChatMessage)
            .where(AgentChatMessage.agent_chat_id == chat.id)
        ) or 0
        if msg_count == 0:
            return
        try:
            await run_summary_for_chat(db, chat=chat)
        except Exception as e:
            print(f"[plaza] summary failed chat_id={chat_id}: {e}")


async def _existing_match_response(
    db: AsyncSession,
    match: Match,
    host_user_id: int,
) -> PlazaInitiateResponse | None:
    running = await db.scalar(
        select(func.count()).select_from(AgentChat).where(
            AgentChat.match_id == match.id,
            AgentChat.status == "running",
        )
    ) or 0
    if running or match.status == "agent_chat_running":
        return PlazaInitiateResponse(
            status="already_running",
            match_id=match.id,
            message="你的 Agent 已经在路上了。聊完会回到个人房间跟你交底。",
        )

    summary = await db.scalar(
        select(Summary)
        .join(AgentChat, AgentChat.id == Summary.agent_chat_id)
        .where(
            AgentChat.match_id == match.id,
            Summary.host_user_id == host_user_id,
            Summary.summary_type == "agent_chat",
        )
        .order_by(Summary.created_at.desc())
        .limit(1)
    )
    if summary is not None:
        return PlazaInitiateResponse(
            status="already_done",
            match_id=match.id,
            summary_id=summary.id,
            message="你的 Agent 已经认识过 TA 了,去个人房间看那份简报。",
        )
    return None


async def _soft_blocked_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = (await db.execute(
        select(UserSoftBlocklist).where(
            or_(
                UserSoftBlocklist.user_id == user_id,
                UserSoftBlocklist.blocked_user_id == user_id,
            )
        )
    )).scalars().all()
    out: set[int] = set()
    for row in rows:
        out.add(row.user_id if row.user_id != user_id else row.blocked_user_id)
    return out


async def _plaza_links(
    db: AsyncSession,
    node_ids: list[int],
) -> dict[tuple[int, int], Literal["shallow_probe", "deep_chat", "human_chat"]]:
    if len(node_ids) < 2:
        return {}

    matches = (await db.execute(
        select(Match).where(
            Match.user_a_id.in_(node_ids),
            Match.user_b_id.in_(node_ids),
        ).limit(32)
    )).scalars().all()
    if not matches:
        return {}

    match_ids = [m.id for m in matches]
    active_sessions = set((await db.execute(
        select(ChatSession.match_id).where(
            ChatSession.match_id.in_(match_ids),
            ChatSession.status == "active",
        )
    )).scalars().all())
    running_chats = set((await db.execute(
        select(AgentChat.match_id).where(
            AgentChat.match_id.in_(match_ids),
            AgentChat.status == "running",
        )
    )).scalars().all())
    done_chats = set((await db.execute(
        select(AgentChat.match_id).where(
            AgentChat.match_id.in_(match_ids),
            AgentChat.status.in_(["done_natural", "done_terminated", "re_dispatched"]),
        )
    )).scalars().all())

    out: dict[tuple[int, int], Literal["shallow_probe", "deep_chat", "human_chat"]] = {}
    for match in matches:
        pair = (match.user_a_id, match.user_b_id)
        if match.id in active_sessions:
            out[pair] = "human_chat"
        elif match.id in running_chats or match.id in done_chats or match.status.startswith("agent_chat"):
            out[pair] = "deep_chat"
        else:
            out[pair] = "shallow_probe"
    return out


def _ordered_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _connection_label(profile_json: dict) -> str | None:
    return (
        ((profile_json.get("relationship_warmth") or {}).get("connection_value") or {})
        .get("label")
    )


def _public_hooks(domains: list[str], connection_label: str | None) -> list[str]:
    hooks = list(domains[:3])
    if connection_label:
        hooks.append(connection_label)
    return hooks[:4]


def _stable_coord(user_id: int, axis: Literal["x", "y"]) -> float:
    digest = hashlib.sha256(f"plaza:{axis}:{user_id}".encode()).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    if axis == "x":
        return round(8 + raw * 84, 2)
    # 上下留出一些空间,避免气泡贴边
    return round(14 + raw * 72, 2)


def _fallback_matchpoint(a_md: MdDocument, b_md: MdDocument) -> MatchpointDraft:
    a_domains = list(a_md.domains_interested or [])
    b_domains = list(b_md.domains_interested or [])
    shared = next((d for d in a_domains if d in b_domains), None)
    if shared:
        explain = f"都对 {shared} 感兴趣"
        source = f"domains.interested[{shared}]"
    else:
        label = _connection_label(a_md.profile_json) or _connection_label(b_md.profile_json) or "开放试探"
        explain = f"广场主动试探 · {label}"
        source = "relationship_warmth.connection_value"
    return MatchpointDraft(
        category="兴趣",
        match_type="广场主动试探",
        similarity=0.5,
        weight=0.4,
        a_source_segments=[source],
        b_source_segments=[source],
        explain=explain,
    )


def _make_matchpoint(match_id: int, draft: MatchpointDraft) -> Matchpoint:
    return Matchpoint(
        match_id=match_id,
        category=draft.category,
        match_type=draft.match_type,
        a_source_segments=draft.a_source_segments,
        b_source_segments=draft.b_source_segments,
        similarity=draft.similarity,
        weight=draft.weight,
    )
