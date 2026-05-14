from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, UserProfile
from src.auth.password import hash_password


def _profile_payload(**overrides):
    profile = {
        "nickname": "新的昵称",
        "age_band": "25-30",
        "gender": "prefer_not_to_say",
        "mbti": "INFJ",
        "avatar_url": None,
    }
    profile.update(overrides)
    return {"profile": profile}


async def _create_bare_user(db_session: AsyncSession) -> User:
    user = User(
        username="bare_profile_user",
        password_hash=hash_password("correct-password"),
        google_name="bare_profile_user",
        is_adult_confirmed=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_me_requires_login(client: AsyncClient):
    resp = await client.get("/api/auth/me")

    assert resp.status_code == 401


async def test_me_returns_user_and_profile_after_login(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.get("/api/auth/me")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == mock_user.id
    assert body["username"] == "mock_user"
    assert body["google_avatar_url"] == "https://lh3.googleusercontent.com/a/mock"
    assert body["profile"]["nickname"] == "Mock"
    assert body["profile"]["mbti"] == "INFJ"


async def test_put_profile_first_write_sets_onboarded_at(
    client: AsyncClient,
    db_session: AsyncSession,
    login_as,
):
    user = await _create_bare_user(db_session)
    login_as(user.id)

    resp = await client.put("/api/auth/me/profile", json=_profile_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarded_at"] is not None
    await db_session.refresh(user)
    assert user.onboarded_at is not None
    assert datetime.fromisoformat(body["onboarded_at"]) == user.onboarded_at


async def test_put_profile_second_write_keeps_existing_onboarded_at(
    client: AsyncClient,
    db_session: AsyncSession,
    login_as,
):
    user = await _create_bare_user(db_session)
    login_as(user.id)
    first = await client.put("/api/auth/me/profile", json=_profile_payload())
    assert first.status_code == 200
    first_onboarded_at = first.json()["onboarded_at"]

    second = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(nickname="第二次昵称"),
    )

    assert second.status_code == 200
    assert second.json()["onboarded_at"] == first_onboarded_at
    profile = (
        await db_session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
    ).scalar_one()
    assert profile.nickname == "第二次昵称"


async def test_put_profile_accepts_https_avatar_url(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url="https://example.com/avatar.jpg"),
    )

    assert resp.status_code == 200
    assert resp.json()["profile"]["avatar_url"] == "https://example.com/avatar.jpg"


async def test_put_profile_accepts_jpeg_data_url(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url="data:image/jpeg;base64,aGVsbG8="),
    )

    assert resp.status_code == 200
    assert resp.json()["profile"]["avatar_url"] == "data:image/jpeg;base64,aGVsbG8="


async def test_put_profile_rejects_text_html_data_url(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url="data:text/html;base64,PGgxPmJvb208L2gxPg=="),
    )

    assert resp.status_code == 422


async def test_put_profile_rejects_javascript_avatar_url(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url="javascript:alert(1)"),
    )

    assert resp.status_code == 422


async def test_put_profile_turns_empty_avatar_url_into_none(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url=""),
    )

    assert resp.status_code == 200
    assert resp.json()["profile"]["avatar_url"] is None


async def test_put_profile_rejects_avatar_url_over_200kb(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)
    oversized = "data:image/jpeg;base64," + ("a" * 200_000)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(avatar_url=oversized),
    )

    assert resp.status_code == 422


async def test_put_profile_rejects_svg_data_url(
    client: AsyncClient,
    mock_user: User,
    login_as,
):
    login_as(mock_user.id)

    resp = await client.put(
        "/api/auth/me/profile",
        json=_profile_payload(
            avatar_url="data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+PC9zdmc+"
        ),
    )

    assert resp.status_code == 422
