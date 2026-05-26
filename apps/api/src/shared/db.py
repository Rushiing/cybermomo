"""
async DB engine + session factory

用法:
    from src.shared.db import get_session

    async def some_endpoint(session: AsyncSession = Depends(get_session)):
        ...
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.shared.settings import get_settings


def _make_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.is_dev,
        # 连接池:SSE 流式 endpoint + BackgroundTask LLM 都会长时间持有连接。
        # 关键约束 — 这是 **per-worker** 配置,uvicorn --workers N 时总连接数
        # = N × (pool_size + max_overflow)。Railway Postgres max_connections=100
        # (superuser_reserved=3 → usable 97)。
        # workers=4 × (10+10)=80 < 97,留 17 给 migration / cron / admin。
        # 改 workers 数时这里要同步算,别撞爆 PG 连接上限。
        pool_size=10,
        max_overflow=10,
        # pool_recycle 强制每 30 分钟回收一次,防止 Railway PG 被 NAT 断开
        pool_recycle=1800,
        # 借连接超时:30s 内拿不到就抛,优于 hang 等 → 暴露问题
        pool_timeout=30,
    )


engine: AsyncEngine = _make_engine()

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency 注入用"""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
