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


def test_summary_system_template_uses_decision_tree_with_bidirectional_and():
    """verdict prompt 是决策树 + 双向 AND(不是单侧信号就拍来电)

    校准史(都用 mock-vs-mock 8 轮对话验证过):
    - v1 无锚 → 清一色"来电"(LLM 总是给好评)
    - v2 比例锚 30/50/20 + AI 互捧警告 → 94% "再观察"
    - v3 决策树 + 单侧 OR → 87% "来电"(单侧热情骗到判断)
    - v4 决策树 + 双向 AND → 这版,要求"来电"必须双方都有强信号

    本 test 锁住 v4 的关键设计点防回退:
    - 决策树结构(三步)
    - "来电"必须双向(条件 A 两侧延展 + 条件 B 双方 warmth)
    - "再观察"是默认落点不是兜底
    - 不能回退到比例锚那版
    """
    prompt = SUMMARY_SYSTEM_TEMPLATE.format(host_md="{}", peer_block="<PEER>")

    # 决策树结构
    assert "决策树" in prompt
    assert "第一步" in prompt and "第二步" in prompt and "第三步" in prompt

    # v4 核心:双向 AND(防回退到 v3 单侧 OR)
    assert "双向" in prompt
    assert "AND" in prompt
    assert "条件 A" in prompt and "条件 B" in prompt
    # "再观察"是默认落点(防回退到 v3 把它当兜底)
    assert "默认落点" in prompt or "默认应该落" in prompt

    # 三档名仍在
    assert "不合" in prompt
    assert "来电" in prompt
    assert "有点意思再观察" in prompt

    # 关键信号字段
    assert "warmth_delta" in prompt
    assert "topic_ref" in prompt
    assert "boundary_hit" in prompt
    assert "来电\"卡片时要克制" in prompt
    assert "还没换场景确认" in prompt
    assert "翻版" in prompt
    assert "灵魂同频" in prompt

    # 反向锁:历史错版字面不能出现
    assert "约 30%" not in prompt
    assert "约 50%" not in prompt
    assert "约 20%" not in prompt
    # v3 错版反向锁
    assert "优先落'来电'" not in prompt and "优先落\"来电\"" not in prompt


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


async def test_laidian_downgrades_without_visible_strong_evidence(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(
            verdict="来电",
            recommended_action="开真人聊天",
        ))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.verdict for s in rows} == {"有点意思再观察"}
    assert {s.recommended_action for s in rows} == {"再派一次"}
    assert all("先不把这场判成来电" in s.risks[0]["text"] for s in rows)


async def test_laidian_allowed_when_transcript_has_visible_bidirectional_push(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, user_a, user_b = await _create_summary_bundle(db_session, with_messages=False)
    db_session.add_all(
        [
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_a.id,
                turn=1,
                topic_ref="topic_a",
                intent="probe",
                utterance="你说喜欢高密度对话，具体是会一直追问到哪一层？",
                public_signals={"intent": "probe"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_b.id,
                turn=2,
                topic_ref="topic_a",
                intent="share",
                utterance="我会追到对方开始说真实选择，而不是只讲观点。你能接受这种强度吗？",
                public_signals={"intent": "share"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_a.id,
                turn=3,
                topic_ref="topic_a",
                intent="share",
                utterance="能接受，但我会看对方是不是也愿意暴露自己的判断成本，不只是审问我。",
                public_signals={"intent": "share"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_b.id,
                turn=4,
                topic_ref="topic_a",
                intent="align",
                utterance="这个公平。我也不喜欢单向审问，所以会先把自己的犹豫摊出来再问人。",
                public_signals={"intent": "align"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_a.id,
                turn=5,
                topic_ref="topic_b",
                intent="probe",
                utterance="那如果聊到边界，你会直接说需要留白，还是先自己往后退一点？",
                public_signals={"intent": "probe"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_b.id,
                turn=6,
                topic_ref="topic_b",
                intent="share",
                utterance="我会直接说，不然对方会误读成冷掉。你刚才问这个，感觉你也在意节奏别被猜。",
                public_signals={"intent": "share"},
                private_signals={"warmth_delta": 1, "topic_interest": 1},
            ),
        ]
    )
    await db_session.commit()
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(
            verdict="来电",
            recommended_action="开真人聊天",
        ))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.verdict for s in rows} == {"来电"}
    assert {s.recommended_action for s in rows} == {"开真人聊天"}


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


async def test_observe_verdict_cannot_recommend_open_chat(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, _, _ = await _create_summary_bundle(db_session)
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(
            verdict="有点意思再观察",
            recommended_action="开真人聊天",
        ))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.verdict for s in rows} == {"有点意思再观察"}
    assert {s.recommended_action for s in rows} == {"再派一次"}


async def test_visible_mismatch_forces_buhe_verdict(
    db_session: AsyncSession,
    monkeypatch,
):
    chat, user_a, user_b = await _create_summary_bundle(db_session, with_messages=False)
    db_session.add_all(
        [
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_a.id,
                turn=1,
                topic_ref="party_pace",
                intent="probe",
                utterance="我喜欢临时被朋友拉去很热闹的局，你会觉得刺激还是累？",
                public_signals={"intent": "probe"},
                private_signals={"warmth_delta": 0, "topic_interest": 0},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_b.id,
                turn=2,
                topic_ref="party_pace",
                intent="deflect",
                utterance="这个我不太在这，太吵和太临时的局我基本接不住。",
                public_signals={"intent": "deflect"},
                private_signals={"warmth_delta": -1, "topic_interest": -1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_a.id,
                turn=3,
                topic_ref="party_pace",
                intent="probe",
                utterance="但如果是熟人临时喊你，给个面子也不行吗？",
                public_signals={"intent": "probe"},
                private_signals={"warmth_delta": -1, "topic_interest": -1},
            ),
            AgentChatMessage(
                agent_chat_id=chat.id,
                speaker_user_id=user_b.id,
                turn=4,
                topic_ref="party_pace",
                intent="reject",
                utterance="不太行，这个节奏对我就是不合适，我会直接拒绝。",
                public_signals={"intent": "reject"},
                private_signals={"warmth_delta": -1, "topic_interest": -1, "boundary_hit": "边界"},
            ),
        ]
    )
    await db_session.commit()
    monkeypatch.setattr(
        "src.summary.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_summary_payload(
            verdict="有点意思再观察",
            recommended_action="再派一次",
        ))),
    )

    await run_summary_for_chat(db_session, chat=chat)
    rows = (await db_session.execute(select(Summary))).scalars().all()

    assert {s.verdict for s in rows} == {"不合"}
    assert {s.recommended_action for s in rows} == {"跟我聊聊调方向"}
    assert all("我会把这场判成不合" in s.highlights[0]["text"] for s in rows)


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
