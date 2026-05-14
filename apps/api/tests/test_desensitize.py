import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.password import hash_password
from src.match.desensitize import (
    _bucketize_dimensions,
    _extract_safe_profile_summary,
    _parse_loose_json,
    run_desensitize_for_match,
)
from src.match.models import Match, MatchHook, Matchpoint
from src.md.models import MdDocument


class FakeLLMResp:
    def __init__(self, text: str):
        self.text = text


def _profile_with_private_text() -> dict:
    return {
        "domains": {"interested": ["文学写作"], "avoided": ["体育赛事"]},
        "raw_answers": {
            "E1": {"option_text": "我喜欢深夜独自读小说"},
        },
        "dialogue": {
            "social_energy": 80,
            "sharing_drive": None,
        },
        "relationship_warmth": {
            "connection_value": {"label": "共鸣连接"},
            "warmth_initiation": {"label": "留意但克制"},
            "support_style": {"label": "问题理解型"},
        },
        "portrait": {
            "body": ["你是个慢热但深度的人"],
        },
    }


def test_extract_safe_profile_summary_does_not_expose_raw_answers():
    profile = _profile_with_private_text()

    result = _extract_safe_profile_summary(profile)
    bucketized = _bucketize_dimensions(profile)

    assert "深夜独自读小说" not in json.dumps(result, ensure_ascii=False)
    assert "深夜独自读小说" not in json.dumps(bucketized, ensure_ascii=False)


def test_extract_safe_profile_summary_does_not_expose_portrait_body():
    result = _extract_safe_profile_summary(_profile_with_private_text())

    assert "慢热但深度" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize(
    ("score", "bucket"),
    [
        (80, "高"),
        (50, "中"),
        (20, "低"),
        (67, "高"),
        (66, "中"),
        (34, "低"),
        (35, "中"),
    ],
)
def test_bucketize_dimensions_uses_three_buckets(score: int, bucket: str):
    result = _bucketize_dimensions({"dialogue": {"social_energy": score}})

    assert result["social_energy"] == bucket


def test_bucketize_dimensions_skips_none_values():
    result = _bucketize_dimensions(
        {"dialogue": {"social_energy": 80, "sharing_drive": None}}
    )

    assert result["social_energy"] == "高"
    assert "sharing_drive" not in result


def test_parse_loose_json_accepts_fenced_and_plain_json():
    assert _parse_loose_json('```json\n{"x":1}\n```') == {"x": 1}
    assert _parse_loose_json('{"x":1}') == {"x": 1}
    assert _parse_loose_json("garbage") is None


async def _create_user(db: AsyncSession, username: str) -> User:
    user = User(
        username=username,
        password_hash=hash_password("correct-password"),
        google_name=username,
        is_adult_confirmed=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _create_match_with_profiles(db: AsyncSession) -> tuple[Match, list[str]]:
    user_a = await _create_user(db, "desensitize_a")
    user_b = await _create_user(db, "desensitize_b")
    a_raw_text = "我喜欢深夜独自读小说"
    b_raw_text = "我会把周末留给山里徒步"
    a_profile = {
        **_profile_with_private_text(),
        "raw_answers": {"E1": {"option_text": a_raw_text}},
    }
    b_profile = {
        **_profile_with_private_text(),
        "raw_answers": {"E1": {"option_text": b_raw_text}},
        "domains": {"interested": ["旅行城市"], "avoided": ["商业财经"]},
    }
    db.add_all(
        [
            MdDocument(
                user_id=user_a.id,
                version=1,
                profile_json=a_profile,
                profile_version="test",
                portrait_body="private portrait",
                domains_interested=["文学写作"],
                domains_avoided=["体育赛事"],
                raw_answers=a_profile["raw_answers"],
                is_active=True,
            ),
            MdDocument(
                user_id=user_b.id,
                version=1,
                profile_json=b_profile,
                profile_version="test",
                portrait_body="private portrait",
                domains_interested=["旅行城市"],
                domains_avoided=["商业财经"],
                raw_answers=b_profile["raw_answers"],
                is_active=True,
            ),
        ]
    )
    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        overall_score=0.8123,
        is_wildcard=False,
        status="pending",
    )
    db.add(match)
    await db.flush()
    db.add(
        Matchpoint(
            match_id=match.id,
            category="domains",
            match_type="resonance",
            a_source_segments=[{"segment": "private-a"}],
            b_source_segments=[{"segment": "private-b"}],
            similarity=0.8,
            weight=0.7,
        )
    )
    await db.commit()
    await db.refresh(match)
    return match, [a_raw_text, b_raw_text]


async def test_run_desensitize_for_match_writes_hooks_without_md_raw_text(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    match, raw_texts = await _create_match_with_profiles(db_session)
    monkeypatch.setattr(
        "src.match.desensitize.llm_chat",
        AsyncMock(
            return_value=FakeLLMResp(
                json.dumps(
                    {
                        "hooks_for_a": [
                            {
                                "topic_id": "topic_a",
                                "category": "domains",
                                "match_type": "resonance",
                                "hook_text": "TA 对夜晚和文字的关系有一点隐秘的共鸣,可以从阅读节奏聊起。",
                                "sensitivity_level": 1,
                                "matchpoint_ref": 0,
                            }
                        ],
                        "hooks_for_b": [
                            {
                                "topic_id": "topic_b",
                                "category": "domains",
                                "match_type": "resonance",
                                "hook_text": "TA 也偏好低噪声的探索,适合从安静的周末安排切入。",
                                "sensitivity_level": 1,
                                "matchpoint_ref": 0,
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        ),
    )

    hooks = await run_desensitize_for_match(db_session, match=match)

    assert len(hooks) == 2
    rows = (await db_session.execute(select(MatchHook))).scalars().all()
    assert len(rows) == 2
    for hook in rows:
        for raw_text in raw_texts:
            assert raw_text not in hook.hook_text, (
                f"hook_text leaked raw .md answer {raw_text!r}: {hook.hook_text}"
            )


async def test_run_desensitize_for_match_invalid_json_returns_empty_without_raise(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    match, _ = await _create_match_with_profiles(db_session)
    monkeypatch.setattr(
        "src.match.desensitize.llm_chat",
        AsyncMock(return_value=FakeLLMResp("this is not json")),
    )

    hooks = await run_desensitize_for_match(db_session, match=match)

    assert hooks == []
    rows = (await db_session.execute(select(MatchHook))).scalars().all()
    assert rows == []
