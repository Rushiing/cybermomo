import json
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.engine import PLATFORM_SYSTEM, _ask_one_turn, run_agent_chat
from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.models import User, UserProfile
from src.auth.password import hash_password
from src.match.models import Match, MatchHook, Matchpoint
from src.md.models import MdDocument


class FakeLLMResp:
    def __init__(self, text: str):
        self.text = text


def _llm_payload(intent: str = "share", *, boundary_hit=None, topic_ref: str = "topic_a") -> str:
    return json.dumps(
        {
            "intent": intent,
            "topic_ref": topic_ref,
            "utterance": f"{intent} utterance",
            "public_signals": {"intent": intent, "topic_ref": topic_ref},
            "private_signals": {
                "warmth_delta": 0,
                "topic_interest": 0,
                "disclosure_level": 1,
                "boundary_hit": boundary_hit,
                "rewrite_level": 0,
            },
            "topic_close_payload": None,
        },
        ensure_ascii=False,
    )


async def _create_user_with_profile(
    db: AsyncSession,
    username: str,
    *,
    age_band: str = "25-30",
    gender: str = "female",
    nickname: str | None = None,
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
            nickname=nickname or username,
            age_band=age_band,
            gender=gender,
            mbti="INFJ",
        )
    )
    db.add(
        MdDocument(
            user_id=user.id,
            version=1,
            profile_json={
                "domains": {"interested": ["文学写作"], "avoided": []},
                "dialogue": {"social_energy": 50},
                "portrait": {"body": ["测试 portrait"]},
            },
            profile_version="test",
            portrait_body="测试 portrait",
            domains_interested=["文学写作"],
            domains_avoided=[],
            raw_answers={},
            is_active=True,
        )
    )
    return user


async def _create_match_bundle(
    db: AsyncSession,
    *,
    with_hooks: bool = True,
    with_b_profile: bool = True,
) -> tuple[Match, User, User]:
    user_a = await _create_user_with_profile(db, "agent_chat_a", gender="female", nickname="阿A")
    if with_b_profile:
        user_b = await _create_user_with_profile(db, "agent_chat_b", gender="male", nickname="阿B")
    else:
        user_b = User(
            username="agent_chat_b",
            password_hash=hash_password("correct-password"),
            google_name="agent_chat_b",
            is_adult_confirmed=True,
        )
        db.add(user_b)
        await db.flush()
    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        overall_score=0.8,
        is_wildcard=False,
        status="pending",
    )
    db.add(match)
    await db.flush()
    mp = Matchpoint(
        match_id=match.id,
        category="domains",
        match_type="resonance",
        a_source_segments=[],
        b_source_segments=[],
        similarity=0.8,
        weight=0.7,
    )
    db.add(mp)
    await db.flush()
    if with_hooks:
        db.add_all(
            [
                MatchHook(
                    match_id=match.id,
                    target_user_id=user_a.id,
                    matchpoint_id=mp.id,
                    topic_id="topic_a",
                    category="domains",
                    match_type="resonance",
                    hook_text="给 A 的钩子",
                    sensitivity_level=1,
                ),
                MatchHook(
                    match_id=match.id,
                    target_user_id=user_b.id,
                    matchpoint_id=mp.id,
                    topic_id="topic_b",
                    category="domains",
                    match_type="resonance",
                    hook_text="给 B 的钩子",
                    sensitivity_level=1,
                ),
            ]
        )
    await db.commit()
    await db.refresh(match)
    return match, user_a, user_b


def test_platform_system_keeps_anti_synthetic_constraints():
    assert '反"装"硬约束' in PLATFORM_SYSTEM
    assert "禁用开场套话" in PLATFORM_SYSTEM
    assert "禁用结尾甩问" in PLATFORM_SYSTEM
    assert "禁用 AI 客气助词" in PLATFORM_SYSTEM
    assert "真人最后会读这场聊天" in PLATFORM_SYSTEM
    assert "两个 AI 在客气地互相恭维" in PLATFORM_SYSTEM
    assert "很高兴认识你" in PLATFORM_SYSTEM
    # peer demographic 不当谈资(voice audit 2026-05-15 命中 chat_id=56:
    # "ESTJ应该挺果断的吧?" / "INTP应该更爱先想透吧?" — peer MBTI 字段
    # 不该出现在 utterance 里,只用来 calibrate 自己这一侧语气)
    assert "禁用把 peer demographic 当谈资抛出" in PLATFORM_SYSTEM
    assert "calibrate 你这一侧 Agent" in PLATFORM_SYSTEM


async def test_turn_prompt_template_injects_peer_block(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, _ = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload())

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=1,
        max_turns=2,
        md_profile_text="",
        hooks=(await db_session.execute(select(MatchHook))).scalars().all(),
        history=[],
        avoid_topic_refs=[],
        peer_block="<MOCK_PEER_BLOCK>",
    )

    assert "<MOCK_PEER_BLOCK>" in captured_prompts[0]


async def test_turn_prompt_template_injects_voice_card(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, _ = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload())

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=1,
        max_turns=10,
        md_profile_text="profile text",
        voice_card_text="<VOICE_CARD>",
        hooks=(await db_session.execute(select(MatchHook))).scalars().all(),
        history=[],
        avoid_topic_refs=[],
    )

    assert "你的内部说话策略" in captured_prompts[0]
    assert "<VOICE_CARD>" in captured_prompts[0]
    assert "第 8 轮之前不要自然收尾" in captured_prompts[0]


async def test_topic_strategy_nudges_after_sticky_topic(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, user_b = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload(topic_ref="topic_boundary"))

    hooks = (await db_session.execute(select(MatchHook))).scalars().all()
    hooks.append(
        MatchHook(
            match_id=match.id,
            target_user_id=user_a.id,
            matchpoint_id=1,
            topic_id="topic_boundary",
            category="生活方式",
            match_type="同类共鸣",
            hook_text="聊聊亲密关系里各自需要多少留白",
            sensitivity_level=1,
        )
    )
    history = [
        AgentChatMessage(speaker_user_id=user_a.id, turn=1, topic_ref="topic_a", intent="probe", utterance="a"),
        AgentChatMessage(speaker_user_id=user_b.id, turn=2, topic_ref="topic_a", intent="share", utterance="b"),
        AgentChatMessage(speaker_user_id=user_a.id, turn=3, topic_ref="topic_a", intent="probe", utterance="c"),
        AgentChatMessage(speaker_user_id=user_b.id, turn=4, topic_ref="topic_a", intent="share", utterance="d"),
    ]

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=5,
        max_turns=10,
        md_profile_text="profile text",
        hooks=hooks,
        history=history,
        avoid_topic_refs=[],
    )

    prompt = captured_prompts[0]
    assert "当前话题 topic_a 已连续 4 轮" in prompt
    assert "不要继续深挖 topic_a" in prompt
    assert "topic_boundary" in prompt


async def test_topic_strategy_runs_spark_validation_on_bidirectional_push(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, user_b = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload(topic_ref="topic_a"))

    history = [
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=1,
            topic_ref="topic_a",
            intent="probe",
            utterance="你是会把不确定先拆开，还是先凭直觉往前试一步？",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_b.id,
            turn=2,
            topic_ref="topic_a",
            intent="share",
            utterance="我会先试一步，但会给自己留一个能撤回的台阶，不喜欢纯冲动。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=3,
            topic_ref="topic_a",
            intent="share",
            utterance="这点我能接住。我也不怕试错，但很在意旁边的人能不能一起复盘。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_b.id,
            turn=4,
            topic_ref="topic_a",
            intent="probe",
            utterance="那如果复盘时发现你判断错了，你更希望对方直接指出，还是先缓一下？",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
    ]

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=5,
        max_turns=10,
        md_profile_text="profile text",
        hooks=(await db_session.execute(select(MatchHook))).scalars().all(),
        history=history,
        avoid_topic_refs=[],
    )

    prompt = captured_prompts[0]
    assert "升温验证" in prompt
    assert "来电验证" in prompt
    assert "不要立刻换题" in prompt
    assert "真实相处、边界、节奏或冲突修复" in prompt
    assert "不要继续纯 probe" in prompt
    assert "intent 优先用 align/share" in prompt
    assert "我接得住你的 X" in prompt
    assert "不要继续深挖 topic_a" not in prompt


async def test_topic_strategy_bridges_to_second_confirmation_late_chat(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, user_b = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload(topic_ref="topic_boundary"))

    hooks = (await db_session.execute(select(MatchHook))).scalars().all()
    hooks.append(
        MatchHook(
            match_id=match.id,
            target_user_id=user_b.id,
            matchpoint_id=1,
            topic_id="topic_boundary",
            category="边界",
            match_type="互补吸引",
            hook_text="聊聊冲突后各自需要多久恢复",
            sensitivity_level=1,
        )
    )
    history = [
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=1,
            topic_ref="topic_a",
            intent="probe",
            utterance="你是会把不确定先拆开，还是先凭直觉往前试一步？",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_b.id,
            turn=2,
            topic_ref="topic_a",
            intent="share",
            utterance="我会先试一步，但会给自己留一个能撤回的台阶，不喜欢纯冲动。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=3,
            topic_ref="topic_a",
            intent="share",
            utterance="这点我能接住。我也不怕试错，但很在意旁边的人能不能一起复盘。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_b.id,
            turn=4,
            topic_ref="topic_a",
            intent="probe",
            utterance="那如果复盘时发现你判断错了，你更希望对方直接指出，还是先缓一下？",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=5,
            topic_ref="topic_a",
            intent="align",
            utterance="直接指出可以，但最好别当场压着我改口，我会想先把判断链复盘完。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_b.id,
            turn=6,
            topic_ref="topic_a",
            intent="align",
            utterance="我也不太吃当场纠偏。能一起复盘就行，别变成谁输谁赢。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
        AgentChatMessage(
            speaker_user_id=user_a.id,
            turn=7,
            topic_ref="topic_a",
            intent="share",
            utterance="对，输赢感一上来我会撤。这个点我觉得你说得挺清楚。",
            private_signals={"warmth_delta": 1, "topic_interest": 1},
        ),
    ]

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_b.id,
        turn_number=8,
        max_turns=10,
        md_profile_text="profile text",
        hooks=hooks,
        history=history,
        avoid_topic_refs=[],
    )

    prompt = captured_prompts[0]
    assert "二次确认" in prompt
    assert "第二个证据面" in prompt
    assert "验证这种顺是否能换场景成立" in prompt
    assert "topic_boundary" in prompt
    assert "不要只靠单一长话题支撑来电" in prompt
    assert "升温验证" not in prompt


async def test_topic_strategy_nudges_mid_chat_coverage(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, user_b = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload())

    history = [
        AgentChatMessage(speaker_user_id=user_a.id, turn=1, topic_ref="topic_a", intent="probe", utterance="a"),
        AgentChatMessage(speaker_user_id=user_b.id, turn=2, topic_ref="topic_a", intent="share", utterance="b"),
    ]

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=5,
        max_turns=10,
        md_profile_text="profile text",
        hooks=(await db_session.execute(select(MatchHook))).scalars().all(),
        history=history,
        avoid_topic_refs=[],
    )

    prompt = captured_prompts[0]
    assert "中段补证据" in prompt
    assert "边界 / 生活节奏 / 真实摩擦" in prompt


async def test_direction_hint_only_injected_for_target_side(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, user_b = await _create_match_bundle(db_session)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload())

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)

    await run_agent_chat(
        db_session,
        match=match,
        max_turns=2,
        direction_hint="多探一下边界感",
        direction_target_user_id=user_a.id,
    )

    assert "宿主新方向指示" in captured_prompts[0]
    assert "多探一下边界感" in captured_prompts[0]
    assert "宿主新方向指示" not in captured_prompts[1]

    match2, user_c, user_d = await _create_match_bundle(db_session)
    captured_prompts.clear()
    await run_agent_chat(
        db_session,
        match=match2,
        max_turns=2,
        direction_hint="换个音乐话题",
        direction_target_user_id=user_d.id,
    )

    assert "宿主新方向指示" not in captured_prompts[0]
    assert "宿主新方向指示" in captured_prompts[1]
    assert "换个音乐话题" in captured_prompts[1]


async def test_avoid_topic_refs_render_redispatch_block(
    db_session: AsyncSession,
    monkeypatch,
):
    match, user_a, _ = await _create_match_bundle(db_session)
    chat = AgentChat(match_id=match.id, status="running")
    db_session.add(chat)
    await db_session.commit()
    await db_session.refresh(chat)
    captured_prompts: list[str] = []

    async def fake_llm_chat(*_args, **kwargs):
        captured_prompts.append(kwargs["messages"][0].content)
        return FakeLLMResp(_llm_payload())

    monkeypatch.setattr("src.agent_chat.engine.llm_chat", fake_llm_chat)
    hooks = (await db_session.execute(select(MatchHook))).scalars().all()
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=1,
        max_turns=2,
        md_profile_text="",
        hooks=hooks,
        history=[],
        avoid_topic_refs=["topic_a", "topic_b"],
    )
    await _ask_one_turn(
        db_session,
        chat=chat,
        speaker_user_id=user_a.id,
        turn_number=1,
        max_turns=2,
        md_profile_text="",
        hooks=hooks,
        history=[],
        avoid_topic_refs=[],
    )

    assert "再派一次" in captured_prompts[0]
    assert "topic_a" in captured_prompts[0]
    assert "topic_b" in captured_prompts[0]
    assert "再派一次" not in captured_prompts[1]


async def test_boundary_hit_tielv_terminates_chat(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    monkeypatch.setattr(
        "src.agent_chat.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(_llm_payload(boundary_hit="铁律"))),
    )

    chat = await run_agent_chat(db_session, match=match, max_turns=4)

    assert chat.status == "done_terminated"
    assert chat.end_reason == "boundary_hit_铁律"


async def test_two_consecutive_wraps_finish_naturally(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    responses = [
        FakeLLMResp(_llm_payload("share")),
        FakeLLMResp(_llm_payload("align")),
        FakeLLMResp(_llm_payload("wrap")),
        FakeLLMResp(_llm_payload("wrap")),
    ]
    monkeypatch.setattr("src.agent_chat.engine.llm_chat", AsyncMock(side_effect=responses))

    chat = await run_agent_chat(
        db_session,
        match=match,
        max_turns=4,
        min_turns_before_wrap=0,
    )

    assert chat.status == "done_natural"
    assert chat.end_reason == "natural_wrap"


async def test_early_wraps_do_not_finish_before_min_turns(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    responses = [FakeLLMResp(_llm_payload("wrap")) for _ in range(6)]
    monkeypatch.setattr("src.agent_chat.engine.llm_chat", AsyncMock(side_effect=responses))

    chat = await run_agent_chat(
        db_session,
        match=match,
        max_turns=6,
        min_turns_before_wrap=8,
    )
    messages = (await db_session.execute(
        select(AgentChatMessage).where(AgentChatMessage.agent_chat_id == chat.id)
    )).scalars().all()

    assert chat.status == "done_natural"
    assert chat.end_reason == "turn_limit"
    assert len(messages) == 6


async def test_non_dict_signals_do_not_crash_chat(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    payload = json.loads(_llm_payload())
    payload["public_signals"] = "bad public"
    payload["private_signals"] = "bad private"
    monkeypatch.setattr(
        "src.agent_chat.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(json.dumps(payload, ensure_ascii=False))),
    )

    chat = await run_agent_chat(db_session, match=match, max_turns=1)
    messages = (
        await db_session.execute(
            select(AgentChatMessage).where(AgentChatMessage.agent_chat_id == chat.id)
        )
    ).scalars().all()

    assert chat.status == "done_natural"
    assert messages[0].public_signals == {}
    assert messages[0].private_signals == {}


async def test_non_object_json_response_becomes_parse_error(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    monkeypatch.setattr(
        "src.agent_chat.engine.llm_chat",
        AsyncMock(return_value=FakeLLMResp(json.dumps("not an object"))),
    )

    chat = await run_agent_chat(db_session, match=match, max_turns=1)

    assert chat.status == "done_terminated"
    assert chat.end_reason == "parse_error"


async def test_agent_chat_repairs_malformed_json_once(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session)
    llm = AsyncMock(side_effect=[
        FakeLLMResp("intent=share; utterance=我先接这个点"),
        FakeLLMResp(_llm_payload("share")),
    ])
    monkeypatch.setattr("src.agent_chat.engine.llm_chat", llm)

    chat = await run_agent_chat(db_session, match=match, max_turns=1)
    messages = (
        await db_session.execute(
            select(AgentChatMessage).where(AgentChatMessage.agent_chat_id == chat.id)
        )
    ).scalars().all()

    assert chat.status == "done_natural"
    assert chat.end_reason == "turn_limit"
    assert len(messages) == 1
    assert llm.await_count == 2


async def test_no_hooks_terminates_chat_without_llm(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session, with_hooks=False)
    llm = AsyncMock()
    monkeypatch.setattr("src.agent_chat.engine.llm_chat", llm)

    chat = await run_agent_chat(db_session, match=match, max_turns=2)

    assert chat.status == "done_terminated"
    assert chat.end_reason == "no_hooks"
    llm.assert_not_called()


async def test_missing_profile_terminates_chat_without_llm(
    db_session: AsyncSession,
    monkeypatch,
):
    match, _, _ = await _create_match_bundle(db_session, with_b_profile=False)
    llm = AsyncMock()
    monkeypatch.setattr("src.agent_chat.engine.llm_chat", llm)

    chat = await run_agent_chat(db_session, match=match, max_turns=2)

    assert chat.status == "done_terminated"
    assert chat.end_reason == "missing_profile"
    llm.assert_not_called()
