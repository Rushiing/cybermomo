"""
Auth 依赖注入

Phase 0 / Phase 1 早期:用 mock 注入(X-Mock-User-Id 头)
Phase 1 OAuth 接入后:替换为 JWT cookie 解析,签名同名函数 get_current_user

mock 在 dev 环境下会自动 upsert 占位用户(让前端联调不需要手工建库)。
"""
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, UserProfile
from src.shared.db import get_session
from src.shared.settings import get_settings


async def get_current_user(
    x_mock_user_id: Annotated[Optional[str], Header(alias="X-Mock-User-Id")] = None,
    db: AsyncSession = Depends(get_session),
) -> User:
    """
    返回当前登录的 User 实体。

    MVP 早期:仅支持 mock(头部 X-Mock-User-Id)。
    生产环境:替换为 OAuth JWT 解析。
    """
    settings = get_settings()

    if x_mock_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录 — Phase 1 接 OAuth 前可用 X-Mock-User-Id 头(dev only)",
        )

    try:
        uid = int(x_mock_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Mock-User-Id 必须是整数",
        )

    # 查用户
    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()

    if user is None:
        if not settings.is_dev:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"user_id={uid} 不存在",
            )
        # dev 环境自动 upsert 一个占位 user(让前端联调不卡)
        user = User(
            id=uid,
            google_sub=f"mock-{uid}",
            email=f"mock-{uid}@cybermomo.dev",
            google_name=f"MockUser{uid}",
            is_adult_confirmed=True,
        )
        db.add(user)
        # 同步建一个最简 profile
        profile = UserProfile(user_id=uid, nickname=f"Mock{uid}")
        db.add(profile)
        await db.commit()
        await db.refresh(user)

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
