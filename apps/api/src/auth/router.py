"""
01 · 用户注册 · API router

Phase 0 阶段:仅 placeholder + /me。
Google OAuth 完整流程 + JWT session 在 Phase 1 接入。
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.db import get_session

router = APIRouter()


@router.get("/me")
async def me(
    db: AsyncSession = Depends(get_session),
):
    """
    返回当前登录用户的最小 profile。

    TODO Phase 1:从 JWT cookie 取 user_id,SELECT users + user_profiles 返回。
    现在仅占位。
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="auth/me 未实现 — Phase 1 接入 Google OAuth 后启用",
    )


@router.get("/google/login")
async def google_login_redirect():
    """重定向到 Google OAuth 授权页"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth login 未实现 — Phase 1 接入",
    )


@router.get("/google/callback")
async def google_callback():
    """OAuth callback · 换 access_token,upsert users,签发 JWT,设置 cookie"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth callback 未实现 — Phase 1 接入",
    )


@router.post("/logout")
async def logout():
    """清除 session cookie"""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="logout 未实现 — Phase 1 接入",
    )
