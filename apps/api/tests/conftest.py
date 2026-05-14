"""
pytest 全局 fixture(auth 单测共用)

⚠️ 本文件包含**进程级 monkey patch**(下面的 @compiles BigInteger → INTEGER):
    一旦 Python 进程 import 了这个模块,所有 SQLAlchemy 模型对 SQLite 方言的
    BigInteger 列都会编译成 INTEGER。这是为了让 auth.users.id (BigInteger 主键)
    在 SQLite 上能自增 — Postgres BigInteger 自增没问题,SQLite 必须是 INTEGER。

    后果:**生产代码不要 import 此文件**(它在 tests/ 目录下,正常不会被生产引用,
    但加这条警示防新人在 src/ 里写 `from tests.conftest import ...`)。
    如果未来要在多 DB 方言下做 type 测试,这里要重做。
"""
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pgvector.sqlalchemy.vector import VECTOR
from sqlalchemy import BigInteger, JSON, delete, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from main import app
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.agent_self.models import AgentConversation, AgentConversationMessage
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.auth.session import create_session_token
from src.match.models import Match, MatchHook, Matchpoint
from src.md.models import MdDocument
from src.shared.db import get_session
from src.shared.settings import get_settings
from src.summary.models import Summary


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type: BigInteger, _compiler, **_kw) -> str:
    """让 SQLite 把 BigInteger 当 INTEGER(进程级,见文件头警示)"""
    return "INTEGER"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type: JSONB, compiler, **kw) -> str:
    return compiler.visit_JSON(JSON(), **kw)


@compiles(VECTOR, "sqlite")
def _compile_vector_sqlite(_type: VECTOR, _compiler, **_kw) -> str:
    return "JSON"


@pytest_asyncio.fixture(scope="session")
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(UserProfile.__table__.create)
        await conn.run_sync(MdDocument.__table__.create)
        await conn.run_sync(Match.__table__.create)
        await conn.run_sync(Matchpoint.__table__.create)
        await conn.run_sync(MatchHook.__table__.create)
        await conn.run_sync(AgentChat.__table__.create)
        await conn.run_sync(AgentChatMessage.__table__.create)
        await conn.run_sync(Summary.__table__.create)
        await conn.run_sync(AgentConversation.__table__.create)
        await conn.run_sync(AgentConversationMessage.__table__.create)

    yield async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(AgentConversationMessage.__table__.drop)
        await conn.run_sync(AgentConversation.__table__.drop)
        await conn.run_sync(Summary.__table__.drop)
        await conn.run_sync(AgentChatMessage.__table__.drop)
        await conn.run_sync(AgentChat.__table__.drop)
        await conn.run_sync(MatchHook.__table__.drop)
        await conn.run_sync(Matchpoint.__table__.drop)
        await conn.run_sync(Match.__table__.drop)
        await conn.run_sync(MdDocument.__table__.drop)
        await conn.run_sync(UserProfile.__table__.drop)
        await conn.run_sync(User.__table__.drop)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async with session_factory() as session:
        await session.execute(delete(AgentConversationMessage))
        await session.execute(delete(AgentConversation))
        await session.execute(delete(Summary))
        await session.execute(delete(AgentChatMessage))
        await session.execute(delete(AgentChat))
        await session.execute(delete(MatchHook))
        await session.execute(delete(Matchpoint))
        await session.execute(delete(Match))
        await session.execute(delete(MdDocument))
        await session.execute(delete(UserProfile))
        await session.execute(delete(User))
        await session.commit()

    yield

    async with session_factory() as session:
        await session.execute(delete(AgentConversationMessage))
        await session.execute(delete(AgentConversation))
        await session.execute(delete(Summary))
        await session.execute(delete(AgentChatMessage))
        await session.execute(delete(AgentChat))
        await session.execute(delete(MatchHook))
        await session.execute(delete(Matchpoint))
        await session.execute(delete(Match))
        await session.execute(delete(MdDocument))
        await session.execute(delete(UserProfile))
        await session.execute(delete(User))
        await session.commit()


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_session, None)


@pytest.fixture
def login_as(client: AsyncClient) -> Callable[[int], None]:
    def _login_as(user_id: int) -> None:
        client.cookies.set(
            get_settings().session_cookie_name,
            create_session_token(user_id),
        )

    return _login_as


@pytest_asyncio.fixture
async def mock_user(db_session: AsyncSession) -> User:
    user = User(
        username="mock_user",
        password_hash=hash_password("correct-password"),
        email="mock@example.com",
        google_name="Mock User",
        google_avatar_url="https://lh3.googleusercontent.com/a/mock",
        is_adult_confirmed=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserProfile(
            user_id=user.id,
            nickname="Mock",
            age_band="25-30",
            gender="prefer_not_to_say",
            mbti="INFJ",
            avatar_url=None,
        )
    )
    await db_session.commit()
    await db_session.refresh(user)
    loaded = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalar_one()
    return loaded
