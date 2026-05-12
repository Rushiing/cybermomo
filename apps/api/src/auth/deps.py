"""
Auth 依赖注入

认证顺序:
1. Session cookie(JWT)— 走 Google OAuth 后写入,生产环境默认走这条
2. X-Mock-User-Id 头 — 仅 dev env 启用,自动 upsert 占位用户,本地联调用
"""
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, UserProfile
from src.auth.session import read_session_user_id
from src.shared.db import get_session
from src.shared.settings import get_settings


async def get_current_user(
    request: Request,
    x_mock_user_id: Annotated[Optional[str], Header(alias="X-Mock-User-Id")] = None,
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    返回当前登录的 User 实体。

    生产:从 session cookie 读 user_id(OAuth 流程写入)
    dev:cookie 不存在时 fallback 到 X-Mock-User-Id 头(并自动 upsert mock user)
    """
    settings = get_settings()

    # 1. 优先 session cookie
    uid_from_cookie = read_session_user_id(request)
    if uid_from_cookie is not None:
        user = (
            await db.execute(select(User).where(User.id == uid_from_cookie))
        ).scalar_one_or_none()
        if user is not None:
            return user
        # cookie 解出 user_id 但 db 里没这人(账户被删?)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session 关联的用户不存在(可能已删账户)",
        )

    # 2. dev fallback:X-Mock-User-Id 头(prod 直接返 401)
    if not settings.is_dev:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
        )

    if x_mock_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录 — dev 模式可用 X-Mock-User-Id 头",
        )

    try:
        uid = int(x_mock_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Mock-User-Id 必须是整数",
        )

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if user is not None:
        return user

    # dev 环境自动 upsert 一个占位 user(让前端联调不卡)
    # 注:前端 page load 会并发打多个 endpoint,所有都触发 upsert → race。
    # catch IntegrityError 后 re-fetch(谁先 INSERT 谁赢,后到的拿到现存的就好)。
    try:
        user = User(
            id=uid,
            google_sub=f"mock-{uid}",
            email=f"mock-{uid}@cybermomo.dev",
            google_name=f"MockUser{uid}",
            is_adult_confirmed=True,
        )
        db.add(user)
        profile = UserProfile(user_id=uid, nickname=f"Mock{uid}")
        db.add(profile)
        await db.commit()
        await db.refresh(user)
        # 显式指定 id 不自增 sequence,这里手动把它撸到 MAX(id),
        # 避免后续 OAuth 真用户(走 sequence 取 id)撞 pk_users。
        await db.execute(text(
            "SELECT setval("
            "pg_get_serial_sequence('users', 'id'), "
            "GREATEST(COALESCE((SELECT MAX(id) FROM users), 0), 1), true"
            ")"
        ))
        await db.commit()
    except IntegrityError:
        await db.rollback()
        user = (await db.execute(
            select(User).where(User.id == uid)
        )).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="user upsert race condition unresolvable",
            )

    return user


# 直接 Depends 实例,可作为参数的 default value(`current_user: User = CurrentUser`)
CurrentUser = Depends(get_current_user)
