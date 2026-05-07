"""
01 · 用户注册 · API router

- GET    /api/auth/me              当前 user + profile
- PUT    /api/auth/me/profile      upsert profile(同时标记 onboarded_at,首次)
- (Phase 1 末)/google/login + /google/callback + /logout

OAuth 接入前用 X-Mock-User-Id 头(见 src/auth/deps.py)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.auth.schemas import UpsertProfileRequest, UserMeResponse, UserProfilePayload
from src.shared.db import get_session

router = APIRouter()


@router.get("/me", response_model=UserMeResponse)
async def me(
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """返回当前 user + profile(若已建)"""
    # eager-load profile
    stmt = (
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == current_user.id)
    )
    user = (await db.execute(stmt)).scalar_one()
    profile_payload: UserProfilePayload | None = None
    if user.profile is not None:
        profile_payload = UserProfilePayload(
            nickname=user.profile.nickname,
            age_band=user.profile.age_band,
            gender=user.profile.gender,
            mbti=user.profile.mbti,
            avatar_url=user.profile.avatar_url,
        )
    return UserMeResponse(
        id=user.id,
        email=user.email,
        google_name=user.google_name,
        is_adult_confirmed=user.is_adult_confirmed,
        onboarded_at=user.onboarded_at,
        created_at=user.created_at,
        profile=profile_payload,
    )


@router.put("/me/profile", response_model=UserMeResponse)
async def upsert_profile(
    payload: UpsertProfileRequest,
    current_user: User = CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """upsert profile;首次写入时同步设置 onboarded_at"""
    profile_in = payload.profile

    # 查现有 profile
    existing = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = existing.scalar_one_or_none()

    if profile is None:
        profile = UserProfile(
            user_id=current_user.id,
            nickname=profile_in.nickname,
            age_band=profile_in.age_band,
            gender=profile_in.gender,
            mbti=profile_in.mbti,
            avatar_url=profile_in.avatar_url,
        )
        db.add(profile)
    else:
        profile.nickname = profile_in.nickname
        profile.age_band = profile_in.age_band
        profile.gender = profile_in.gender
        profile.mbti = profile_in.mbti
        profile.avatar_url = profile_in.avatar_url

    # 首次完成基础信息 → 标 onboarded_at
    if current_user.onboarded_at is None:
        current_user.onboarded_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(current_user)

    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        google_name=current_user.google_name,
        is_adult_confirmed=current_user.is_adult_confirmed,
        onboarded_at=current_user.onboarded_at,
        created_at=current_user.created_at,
        profile=profile_in,
    )


# ========================================
# OAuth 占位(Phase 1 末实装)
# ========================================

@router.get("/google/login")
async def google_login_redirect():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth login 待 OAuth 配置完成后启用",
    )


@router.get("/google/callback")
async def google_callback():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth callback 待 OAuth 配置完成后启用",
    )


@router.post("/logout")
async def logout():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="logout 待 OAuth 接入后启用",
    )
