"""
03 · 匹配引擎 · API router

- POST /api/match/run        手动触发本人的匹配(dev / debug 用)
- GET  /api/match/me         看本人涉及的 matches 列表
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.deps import CurrentUser
from src.auth.models import User
from src.match import service as match_service
from src.match.models import Match, Matchpoint
from src.match.schemas import (
    MatchpointResponse,
    MatchResponse,
    MatchRunResponse,
)
from src.shared.db import get_session

router = APIRouter()


def _to_match_response(m: Match, mps: Optional[list[Matchpoint]] = None) -> MatchResponse:
    return MatchResponse(
        id=m.id,
        user_a_id=m.user_a_id,
        user_b_id=m.user_b_id,
        overall_score=float(m.overall_score),
        is_wildcard=m.is_wildcard,
        status=m.status,
        created_at=m.created_at,
        matchpoints=[
            MatchpointResponse(
                id=mp.id,
                category=mp.category,
                match_type=mp.match_type,
                similarity=float(mp.similarity),
                weight=float(mp.weight),
            )
            for mp in (mps or [])
        ] if mps is not None else None,
    )


@router.post("/run", response_model=MatchRunResponse)
async def trigger_match(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    手动触发本人的匹配。
    自动:
    - 跳过已经 match 过的对方
    - 跳过软拉黑名单(双向)
    """
    new_matches = await match_service.run_matching_for_user(db, user_id=current_user.id)
    return MatchRunResponse(
        user_id=current_user.id,
        new_matches=len(new_matches),
        matches=[_to_match_response(m) for m in new_matches],
    )


@router.get("/me", response_model=list[MatchResponse])
async def list_my_matches(
    status: Optional[str] = Query(default=None, description="可选过滤:pending / agent_chat_running / agent_chat_done / archived"),
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """读本人涉及的 matches(包含 matchpoints)"""
    matches = await match_service.list_matches_for_user(
        db, user_id=current_user.id, status=status
    )
    if not matches:
        return []

    # 拉 matchpoints
    match_ids = [m.id for m in matches]
    mps = (await db.execute(
        select(Matchpoint).where(Matchpoint.match_id.in_(match_ids))
    )).scalars().all()
    by_match: dict[int, list[Matchpoint]] = {}
    for mp in mps:
        by_match.setdefault(mp.match_id, []).append(mp)

    return [_to_match_response(m, by_match.get(m.id, [])) for m in matches]
