from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, UserProfile
from src.auth.password import hash_password


async def test_register_happy_path_sets_session_cookie_and_returns_user(
    client: AsyncClient,
):
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": "new_user",
            "password": "strong-pass",
            "email": "new@example.com",
            "nickname": "新朋友",
        },
    )

    assert resp.status_code == 201
    assert "cm_session=" in resp.headers["set-cookie"]
    body = resp.json()
    assert body["id"] is not None
    assert body["username"] == "new_user"
    assert body["email"] == "new@example.com"
    assert body["google_name"] == "新朋友"
    assert body["google_avatar_url"] is None
    assert body["is_adult_confirmed"] is False
    assert body["created_at"]
    assert body["profile"] == {
        "nickname": "新朋友",
        "age_band": None,
        "gender": None,
        "mbti": None,
        "avatar_url": None,
    }


async def test_register_duplicate_username_returns_409(client: AsyncClient):
    payload = {"username": "taken_user", "password": "strong-pass"}
    first = await client.post("/api/auth/register", json=payload)

    second = await client.post("/api/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


async def test_register_rejects_invalid_username(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"username": "bad-name", "password": "strong-pass"},
    )

    assert resp.status_code == 422


async def test_register_rejects_short_password(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"username": "short_pass", "password": "short"},
    )

    assert resp.status_code == 422


async def test_login_with_correct_username_and_password_sets_session_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
):
    db_session.add(
        User(
            username="login_user",
            password_hash=hash_password("correct-password"),
            email=None,
            google_name="login_user",
            is_adult_confirmed=False,
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/api/auth/login",
        json={"username": "login_user", "password": "correct-password"},
    )

    assert resp.status_code == 200
    assert "cm_session=" in resp.headers["set-cookie"]
    body = resp.json()
    assert body["username"] == "login_user"
    assert body["profile"] is None


async def test_login_wrong_password_and_missing_user_share_same_401_detail(
    client: AsyncClient,
    db_session: AsyncSession,
):
    db_session.add(
        User(
            username="known_user",
            password_hash=hash_password("correct-password"),
            google_name="known_user",
            is_adult_confirmed=False,
        )
    )
    await db_session.commit()

    wrong_password = await client.post(
        "/api/auth/login",
        json={"username": "known_user", "password": "wrong-password"},
    )
    missing_user = await client.post(
        "/api/auth/login",
        json={"username": "missing_user", "password": "wrong-password"},
    )

    assert wrong_password.status_code == 401
    assert missing_user.status_code == 401
    assert wrong_password.json() == missing_user.json()
    assert wrong_password.json()["detail"] == "用户名或密码错误"


async def test_register_with_nickname_creates_profile_row(
    client: AsyncClient,
    db_session: AsyncSession,
):
    resp = await client.post(
        "/api/auth/register",
        json={
            "username": "profile_user",
            "password": "strong-pass",
            "nickname": "有昵称",
        },
    )
    assert resp.status_code == 201

    user = (
        await db_session.execute(select(User).where(User.username == "profile_user"))
    ).scalar_one()
    profile = (
        await db_session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    assert profile is not None
    assert profile.nickname == "有昵称"


async def test_register_without_nickname_does_not_create_profile_row(
    client: AsyncClient,
    db_session: AsyncSession,
):
    resp = await client.post(
        "/api/auth/register",
        json={"username": "bare_user", "password": "strong-pass"},
    )
    assert resp.status_code == 201

    user = (
        await db_session.execute(select(User).where(User.username == "bare_user"))
    ).scalar_one()
    profile = (
        await db_session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
    ).scalar_one_or_none()

    assert profile is None


async def test_register_then_me_returns_complete_user_response(client: AsyncClient):
    register_resp = await client.post(
        "/api/auth/register",
        json={"username": "me_user", "password": "strong-pass"},
    )
    assert register_resp.status_code == 201

    me_resp = await client.get("/api/auth/me")

    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["id"] == register_resp.json()["id"]
    assert body["username"] == "me_user"
    assert body["email"] is None
    assert body["google_name"] == "me_user"
    assert "google_avatar_url" in body
    assert body["google_avatar_url"] is None
    assert body["is_adult_confirmed"] is False
    assert body["created_at"]
    assert body["profile"] is None
