import json
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.match.models import Match
from src.md.models import MdDocument
from src.summary.engine import SUMMARY_SYSTEM_TEMPLATE, run_summary_for_chat
from src.summary.models import Summary


class FakeLLMResp:
    def __init__(self, text: str):
        self.text = text


def _summary_payload(**overrides) -> str:
    data = {
        "verdict": "有点意思再观察",
        "highlights": [{"text": "有一点接上了", "evidence_utterance_id": 1}],
        "risks": [],
        "recommended_action": "再派一次",
        "evidence_chunks": [{"utterance_id": 1, "speaker": "peer", "text": "嗯,这点能聊"}],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


async def _create_summary_bundle(db: AsyncSession, *, with_messages: bool = True) -> tuple[AgentChat, User, User]:
    users = []
    for username, nickname, gender in [
        ("summary_a", "宿主A", "female"),
        ("summary_b", "对方B", "male"),
    ]:
        user = User(
            username=username,
            password_hash=hash_password("correct-password"),
            google_name=username,
            is_adult_confirmed=True,
        )
        db.add(user)
        await db.flush()
        users.append(user)
        db.add(
            UserProfile(
                user_id=user.id,
                nickname=nickname,
                age_band="25-30",
                gender=gender,
                mbti="INFJ",
            )
        )
        db.add(
            MdDocument(
                user_id=user.id,
                version=1,
                profile_json={
                    "domains": {"interested": ["心理与人类观察"], "avoided": []},
                    "portrait": {"body": ["测试 portrait"]},
                },
                profile_version="test",
                portrait_body="测试 portrait",
                domains_interested=["心理与人类观察"],
                domains_avoided=[],
                raw_answers={},
                is_active=True,
            )
        )
    match = Match(
        user_a_id=users[0].id,
        user_b_id=users[1].id,
        overall_score=0.8,
        is_wildcard=False,
        status="done",
    )
    db.add(match)
    await db.flush()
    chat = AgentChat(match_id=match.id, status="done_natural", end_reason="natural_wrap")
    db.add(chat)
    await db.flush()
    if with_messages:
        db.add_all(
            [
                AgentChatMessage(
                    agent_chat_id=chat.id,
                    speaker_user_id=users[0].id,
                    turn=1,
                    topic_ref="topic_a",
                    intent="share",
                    utterance="我对高密度对话有点兴趣",
                    public_signals={"intent": "share"},
                    private_signals={"warmth_delta": 1, "topic_interest": 1},
                ),
                AgentChatMessage(
                    agent_chat_id=chat.id,
                    speaker_user_id=users[1].id,
                    turn=2,
                    topic_ref="topic_a",
                    intent="align",
                    utterance="嗯,这点能聊",
                    public_signals={"intent": "align"},
                    private_signals={"warmth_delta": 0, "topic_interest": 1},
                ),
            ]
        )
    await db.commit()
    await db.refresh(chat)
    return chat, users[0], users[1]


def test_summary_system_template_uses_decision_tree_not_distribution_quota():
    """verdict prompt 是决策树(按顺序排除"不合"→"来电"→"再观察"),不再用比例锚

    历史背景:第一版 prompt 没分布锚,跑出来清一色"来电"(过度乐观);第二版
    加了"30%/50%/20%"比例锚 + "AI 互捧"警告,跑出来清一色"再观察"(过度保守)。
    第三版改成决策树:**"再观察"是兜底档不是默认档**,必须先排除"不合"和"来电"
    才能落"再观察"。本 test 锁住决策树的关键字面,防止再回退到比例锚那一版。
    """
    prompt = SUMMARY_SYSTEM_TEMPLATE.format(host_md="{}", peer_block="<PEER>")

    # 决策树结构
    assert "决策树" in prompt
    assert "第一步" in prompt and "第二步" in prompt and "第三步" in prompt
    assert "兜底档" in prompt and "不是默认档" in prompt

    # 三档名仍在
    assert "不合" in prompt
    assert "来电" in prompt
    assert "有点意思再观察" in prompt

    # 关键信号字段(给 LLM 看 private/public signals)
    assert "warmth_delta" in prompt
    assert "topic_ref" in prompt
    assert "boundary_hit" in prompt

    # 反向锁:不能再回退到"比例锚"那版
    assert "约 30%" not in prompt
    assert "约 50%" not in prompt
    assert "约 20%" not in prompt


async def test_run_summary_for_chat_creates_two_host_summaries(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, user_a, user_b = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload())),
    )

    summaries = await run_summary_for_chat(db_session, chat=chat)

    assert len(summaries) == 2
    rows = (await db_session.execute(select(Summary))).scalars().all()
    assert {s.host_user_id for s in rows} == {user_a.id, user_b.id}


async def test_invalid_verdict_falls_back_to_observe(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(verdict="非常喜欢"))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.verdict for s in rows} == {"有点意思再观察"}


async def test_invalid_recommended_action_falls_back_to_redispatch(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(recommended_action="立即结婚"))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.recommended_action for s in rows} == {"再派一次"}


async def test_peer_block_is_injected_into_summary_system(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    captured_systems: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_systems.append(kwargs["system"])
        return FakeLLMResp(_summary_payload())

    monkeypatch.setattr("src.summary.engine.llm_chat", fake_llm_chat)
    monkeypatch.setattr("src.summary.engine.format_peer_block", lambda **_kwargs: "<MOCK_PEER>")

    await run_summary_for_chat(db_session, chat=chat)

    assert captured_systems
    assert all("<MOCK_PEER>" in system for system in captured_systems)


async def test_empty_messages_returns_empty_list_without_llm(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session, with_messages=False)
    llm = AsyncMock()
    monkeypatch.setattr("src.summary.engine.llm_chat", llm)

    summaries = await run_summary_for_chat(db_session, chat=chat)

    assert summaries == []
    llm.assert_not_called()


async def test_llm_error_for_one_host_does_not_block_other_host(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(side_effect=[Exception("boom"), FakeLLMResp(_summary_payload())]),
    )

    summaries = await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert len(summaries) == 1
    assert len(rows) == 1
