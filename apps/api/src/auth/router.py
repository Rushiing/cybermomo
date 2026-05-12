"""
01 · 用户注册 · API router

- GET    /api/auth/me              当前 user + profile
- PUT    /api/auth/me/profile      upsert profile(同时标记 onboarded_at,首次)
- GET    /api/auth/google/login    跳转 Google OAuth consent
- GET    /api/auth/google/callback OAuth 回调:exchange code → upsert user → 写 session cookie → 跳 web
- POST   /api/auth/logout          清 session cookie

Dev fallback:src.auth.deps 在 dev env 下支持 X-Mock-User-Id 头(不需要 OAuth)
"""
import secrets
import urllib.parse
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from jose import jwt as jose_jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth.deps import CurrentUser
from src.auth.models import User, UserProfile
from src.auth.schemas import UpsertProfileRequest, UserMeResponse, UserProfilePayload
from src.auth.session import (
    clear_oauth_state_cookie,
    clear_session_cookie,
    read_oauth_state_cookie,
    set_oauth_state_cookie,
    set_session_cookie,
)
from src.shared.db import get_session
from src.shared.settings import get_settings

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
# Google OAuth · 实装
# ========================================
#
# 流程:
# 1. 用户点 "用 Google 登录" → 浏览器 GET /google/login
# 2. 服务端生成 state(CSRF),写 cookie,redirect 到 Google authorize URL
# 3. Google 同意页 → 回调 /google/callback?code=...&state=...
# 4. 校验 state cookie 跟 query state 一致
# 5. POST code 到 Google token endpoint 换 access_token + id_token
# 6. 解 id_token(JWT)拿 sub / email / name / picture
# 7. upsert User by google_sub
# 8. 写 session cookie,redirect 到 web 前端(/room)
#
# 配置(Railway api service Variables):
# - GOOGLE_OAUTH_CLIENT_ID
# - GOOGLE_OAUTH_CLIENT_SECRET
# - GOOGLE_OAUTH_REDIRECT_URI    https://<api-domain>/api/auth/google/callback
# - WEB_BASE_URL                 https://<web-domain>
# - JWT_SECRET                   强随机(`openssl rand -hex 32`),prod 必填
#
# Google Cloud Console:
# - OAuth 2.0 Client ID → Authorized redirect URIs 加上 GOOGLE_OAUTH_REDIRECT_URI


_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_SCOPES = "openid email profile"


def _require_oauth_config():
    settings = get_settings()
    missing: list[str] = []
    if not settings.google_oauth_client_id:
        missing.append("GOOGLE_OAUTH_CLIENT_ID")
    if not settings.google_oauth_client_secret:
        missing.append("GOOGLE_OAUTH_CLIENT_SECRET")
    if not settings.google_oauth_redirect_uri:
        missing.append("GOOGLE_OAUTH_REDIRECT_URI")
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OAuth 未配置:缺 {', '.join(missing)}",
        )


@router.get("/google/login")
async def google_login_redirect():
    """生成 OAuth state,redirect 到 Google authorize"""
    _require_oauth_config()
    settings = get_settings()

    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": _GOOGLE_SCOPES,
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    auth_url = f"{_GOOGLE_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    resp = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    set_oauth_state_cookie(resp, state)
    return resp


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    """Google 回调:验证 state → exchange code → upsert user → 写 session cookie → 跳 web"""
    _require_oauth_config()
    settings = get_settings()

    # 1. 错误参数(用户拒绝同意等)
    if error:
        return _redirect_to_web_with_error(error)

    if not code or not state:
        return _redirect_to_web_with_error("missing_code_or_state")

    # 2. CSRF 校验
    cookie_state = read_oauth_state_cookie(request)
    if not cookie_state or cookie_state != state:
        return _redirect_to_web_with_error("state_mismatch")

    # 3. exchange code → tokens
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": settings.google_oauth_redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as e:
        print(f"[oauth] token exchange failed: {e}")
        return _redirect_to_web_with_error("token_exchange_failed")

    id_token = token_data.get("id_token")
    if not id_token:
        return _redirect_to_web_with_error("no_id_token")

    # 4. 解 id_token(Google 签的 JWT,我们这边按"信任 Google 已签好"读 claims;
    #    严格起见应该用 Google 的 JWKs 验签,但 MVP 阶段够了 — token 来自 HTTPS
    #    response,不是用户传的)
    try:
        claims = jose_jwt.get_unverified_claims(id_token)
    except Exception as e:
        print(f"[oauth] id_token decode failed: {e}")
        return _redirect_to_web_with_error("id_token_decode_failed")

    google_sub = claims.get("sub")
    email = claims.get("email")
    name = claims.get("name")
    picture = claims.get("picture")

    if not google_sub or not email:
        return _redirect_to_web_with_error("incomplete_id_token")

    # 5. upsert User
    user = await _upsert_user_from_google(
        db,
        google_sub=str(google_sub),
        email=str(email),
        name=name,
        picture=picture,
    )

    # 6. 写 session cookie + 跳 web
    next_path = "/room" if user.onboarded_at else "/onboarding"
    resp = RedirectResponse(
        url=f"{settings.web_base_url.rstrip('/')}{next_path}",
        status_code=status.HTTP_302_FOUND,
    )
    set_session_cookie(resp, user.id)
    clear_oauth_state_cookie(resp)
    return resp


async def _upsert_user_from_google(
    db: AsyncSession,
    *,
    google_sub: str,
    email: str,
    name: str | None,
    picture: str | None,
) -> User:
    """根据 google_sub 找用户;不存在就建。"""
    user = (
        await db.execute(select(User).where(User.google_sub == google_sub))
    ).scalar_one_or_none()
    if user is not None:
        # 已存在 — 同步 email / name / picture(允许用户在 Google 改了名字 / 头像)
        changed = False
        if user.email != email:
            user.email = email
            changed = True
        if name and user.google_name != name:
            user.google_name = name
            changed = True
        if picture and user.google_avatar_url != picture:
            user.google_avatar_url = picture
            changed = True
        if changed:
            await db.commit()
            await db.refresh(user)
        return user

    # 新用户
    try:
        user = User(
            google_sub=google_sub,
            email=email,
            google_name=name,
            google_avatar_url=picture,
            is_adult_confirmed=False,  # onboarding 里会勾选
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user
    except IntegrityError as e:
        # 完整异常打到日志方便定位(orig 是 asyncpg / psycopg 的底层异常)
        print(f"[oauth upsert] IntegrityError: {e}; orig={getattr(e, 'orig', None)!r}")
        await db.rollback()
        # 并发场景:谁先 INSERT 谁赢,后到的 re-fetch 拿到现存的
        user = (
            await db.execute(select(User).where(User.google_sub == google_sub))
        ).scalar_one_or_none()
        if user is not None:
            return user
        # 不是并发 — 是真的 INSERT 失败(NOT NULL / CHECK / 其它 UNIQUE)
        # 把底层 SQL 错误 surface 出来,前端能看
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"user upsert failed: {str(getattr(e, 'orig', e))[:300]}",
        )
    except Exception as e:
        # 非 IntegrityError(连接错 / 序列号错 / 等)— 也吐细节出来
        print(f"[oauth upsert] non-integrity error: {type(e).__name__}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"user upsert failed: {type(e).__name__}: {str(e)[:300]}",
        )


def _redirect_to_web_with_error(code: str) -> RedirectResponse:
    """OAuth 出错时 redirect 回 web 首页带 ?auth_error=..."""
    settings = get_settings()
    target = f"{settings.web_base_url.rstrip('/')}/?auth_error={urllib.parse.quote(code)}"
    return RedirectResponse(url=target, status_code=status.HTTP_302_FOUND)


@router.post("/logout")
async def logout():
    """清掉 session cookie。前端拿到 200 后自己 router.push('/')。"""
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(resp)
    return resp
