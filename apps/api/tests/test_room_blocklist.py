from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.room.models import UserSoftBlocklist


async def test_blocklist_returns_blocked_user_nickname(
    client: AsyncClient,
    db_session: AsyncSession,
    login_as,
):
    me = User(
        username="block_owner",
        password_hash=hash_password("correct-password"),
        is_adult_confirmed=True,
    )
    peer = User(
        username="blocked_peer",
        password_hash=hash_password("correct-password"),
        is_adult_confirmed=True,
    )
    db_session.add_all([me, peer])
    await db_session.flush()
    db_session.add(
        UserProfile(
            user_id=peer.id,
            nickname="森屿",
            age_band="25-30",
            gender="prefer_not_to_say",
            mbti=None,
        )
    )
    db_session.add(
        UserSoftBlocklist(
            user_id=me.id,
            blocked_user_id=peer.id,
            reason="dropped from summary card",
        )
    )
    await db_session.commit()
    login_as(me.id)

    resp = await client.get("/api/room/blocklist")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["blocked_user_id"] == peer.id
    assert body[0]["blocked_nickname"] == "森屿"
    assert body[0]["reason"] == "dropped from summary card"
    assert body[0]["created_at"] is not None
