from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import BigInteger, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from main import app
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.auth.session import create_session_token
from src.shared.db import get_session
from src.shared.settings import get_settings


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type: BigInteger, _compiler, **_kw) -> str:
    return "INTEGER"


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

    yield async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(UserProfile.__table__.drop)
        await conn.run_sync(User.__table__.drop)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[None]:
    async with session_factory() as session:
        await session.execute(delete(UserProfile))
        await session.execute(delete(User))
        await session.commit()

    yield

    async with session_factory() as session:
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
