from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat
from src.agent_self.engine import _load_peer_block, _resolve_peer_user_id
from src.agent_self.models import AgentConversation
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.match.models import Match


async def _create_user(
    db: AsyncSession,
    username: str,
    *,
    nickname: str,
    age_band: str = "25-30",
    gender: str = "female",
) -> User:
    user = User(
        username=username,
        password_hash=hash_password("correct-password"),
        google_name=username,
        is_adult_confirmed=True,
    )
    db.add(user)
    await db.flush()
    db.add(
        UserProfile(
            user_id=user.id,
            nickname=nickname,
            age_band=age_band,
            gender=gender,
            mbti="INFJ",
        )
    )
    return user


async def _create_room_context(db: AsyncSession) -> tuple[AgentConversation, AgentConversation, User, User]:
    user_a = await _create_user(db, "self_a", nickname="宿主A", gender="female")
    user_b = await _create_user(db, "self_b", nickname="对方B", gender="male", age_band="30-35")
    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        overall_score=0.8,
        is_wildcard=False,
        status="done",
    )
    db.add(match)
    await db.flush()
    chat = AgentChat(match_id=match.id, status="done_natural", end_reason="natural_wrap")
    db.add(chat)
    await db.flush()
    conv_a = AgentConversation(
        host_user_id=user_a.id,
        scope="room",
        title="room A",
        context_refs={"agent_chat_id": chat.id},
    )
    conv_b = AgentConversation(
        host_user_id=user_b.id,
        scope="room",
        title="room B",
        context_refs={"agent_chat_id": chat.id},
    )
    db.add_all([conv_a, conv_b])
    await db.commit()
    await db.refresh(conv_a)
    await db.refresh(conv_b)
    return conv_a, conv_b, user_a, user_b


async def test_general_scope_resolves_no_peer(db_session: AsyncSession):
    conv = AgentConversation(host_user_id=1, scope="general", context_refs=None)

    assert await _resolve_peer_user_id(db_session, conversation=conv) is None


async def test_revisit_scope_uses_peer_user_id(db_session: AsyncSession):
    conv = AgentConversation(
        host_user_id=1,
        scope="revisit",
        context_refs={"peer_user_id": 5},
    )

    assert await _resolve_peer_user_id(db_session, conversation=conv) == 5


async def test_plaza_scope_uses_target_user_id(db_session: AsyncSession):
    conv = AgentConversation(
        host_user_id=1,
        scope="plaza",
        context_refs={"target_user_id": 8},
    )

    assert await _resolve_peer_user_id(db_session, conversation=conv) == 8


async def test_room_scope_resolves_other_side_from_agent_chat_match(
    db_session: AsyncSession,
):
    conv_a, conv_b, user_a, user_b = await _create_room_context(db_session)

    assert await _resolve_peer_user_id(db_session, conversation=conv_a) == user_b.id
    assert await _resolve_peer_user_id(db_session, conversation=conv_b) == user_a.id


async def test_room_scope_missing_agent_chat_returns_none(db_session: AsyncSession):
    conv = AgentConversation(
        host_user_id=1,
        scope="room",
        context_refs={"agent_chat_id": 99},
    )

    assert await _resolve_peer_user_id(db_session, conversation=conv) is None


async def test_room_scope_missing_match_returns_none(db_session: AsyncSession):
    chat = AgentChat(match_id=42, status="done_natural")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    conv = AgentConversation(
        host_user_id=1,
        scope="room",
        context_refs={"agent_chat_id": chat.id},
    )

    assert await _resolve_peer_user_id(db_session, conversation=conv) is None


async def test_load_peer_block_passes_peer_profile_to_formatter(
    db_session: AsyncSession,
    monkeypatch,
):
    conv_a, _, user_a, user_b = await _create_room_context(db_session)
    captured: dict = {}

    def fake_format_peer_block(**kwargs):
        captured.update(kwargs)
        return "<PEER_BLOCK>"

    monkeypatch.setattr("src.agent_self.engine.format_peer_block", fake_format_peer_block)

    result = await _load_peer_block(db_session, conversation=conv_a)

    assert result == "<PEER_BLOCK>"
    assert captured["peer_user_id"] == user_b.id
    assert captured["peer_nickname"] == "对方B"
    assert captured["peer_gender"] == "male"
    assert captured["host_age_band"] == "25-30"
