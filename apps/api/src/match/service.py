"""
03 · 匹配引擎 · service 层

业务用法:
    new_matches = await run_matching_for_user(db, user_id=42)
触发:
    - 用户首次创建 active .md 时调用一次
    - 后续可加定时 batch
"""
from __future__ import annotations

import json
from typing import Sequence

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.match.engine import (
    CandidateResult,
    MatchpointDraft,
    select_candidates,
)
from src.match.models import Match, Matchpoint
from src.md.models import MdDocument
from src.room.models import UserSoftBlocklist


async def _get_active_profile(db: AsyncSession, user_id: int) -> dict | None:
    md = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id == user_id,
            MdDocument.is_active.is_(True),
        ).limit(1)
    )).scalar_one_or_none()
    return md.profile_json if md else None


async def _candidate_pool(
    db: AsyncSession, exclude_user_id: int
) -> list[tuple[int, dict]]:
    """所有已建 active .md 的其他用户(后续可加按 score 预过滤)"""
    rows = (await db.execute(
        select(MdDocument.user_id, MdDocument.profile_json).where(
            MdDocument.is_active.is_(True),
            MdDocument.user_id != exclude_user_id,
        )
    )).all()
    return [(uid, profile) for uid, profile in rows]


async def _soft_blocked_ids(db: AsyncSession, user_id: int) -> set[int]:
    """user 的软拉黑名单(双向都过滤:我拉黑的 + 拉黑我的)"""
    rows = (await db.execute(
        select(UserSoftBlocklist).where(
            or_(
                UserSoftBlocklist.user_id == user_id,
                UserSoftBlocklist.blocked_user_id == user_id,
            )
        )
    )).scalars().all()
    out: set[int] = set()
    for r in rows:
        out.add(r.user_id if r.user_id != user_id else r.blocked_user_id)
    return out


async def _existing_match_partners(db: AsyncSession, user_id: int) -> set[int]:
    """已经匹配过的对方用户(避免重复创建)"""
    rows = (await db.execute(
        select(Match).where(
            or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
        )
    )).scalars().all()
    out: set[int] = set()
    for m in rows:
        out.add(m.user_b_id if m.user_a_id == user_id else m.user_a_id)
    return out


async def run_matching_for_user(
    db: AsyncSession,
    *,
    user_id: int,
    top_k: int = 5,
) -> list[Match]:
    """
    给定 user_id,跑一次匹配,把 top_k 候选写入 matches + matchpoints。
    返回新创建的 Match 列表(不包含已存在的 pair)。
    """
    a_profile = await _get_active_profile(db, user_id)
    if a_profile is None:
        return []  # 还没建 .md,跳过

    pool_raw = await _candidate_pool(db, user_id)
    if not pool_raw:
        return []

    soft_blocked = await _soft_blocked_ids(db, user_id)
    already_matched = await _existing_match_partners(db, user_id)
    blocked = soft_blocked | already_matched

    candidates = select_candidates(
        user_a_id=user_id,
        user_a_profile=a_profile,
        candidate_pool=pool_raw,
        top_k=top_k,
        soft_blocked=blocked,
    )

    new_matches: list[Match] = []
    for c in candidates:
        # 强制小 id 在前(数据库 CHECK 约束 user_a_id < user_b_id)
        a_id, b_id = (user_id, c.user_b_id) if user_id < c.user_b_id else (c.user_b_id, user_id)
        match = Match(
            user_a_id=a_id,
            user_b_id=b_id,
            overall_score=c.score.overall_score,
            is_wildcard=c.is_wildcard,
            status="pending",
        )
        db.add(match)
        await db.flush()  # 拿 match.id

        for mp in c.score.matchpoints:
            db.add(_make_matchpoint(match.id, mp))

        new_matches.append(match)

    await db.commit()
    return new_matches


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


async def list_matches_for_user(
    db: AsyncSession, *, user_id: int, status: str | None = None
) -> list[Match]:
    """读 user 涉及的所有 matches(用于 debug GET /api/match/me)"""
    stmt = select(Match).where(
        or_(Match.user_a_id == user_id, Match.user_b_id == user_id)
    )
    if status:
        stmt = stmt.where(Match.status == status)
    stmt = stmt.order_by(Match.overall_score.desc())
    return list((await db.execute(stmt)).scalars().all())
