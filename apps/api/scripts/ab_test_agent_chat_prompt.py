#!/usr/bin/env python3
# ruff: noqa: E402
"""
Agent 互聊 prompt A/B 对比脚本。

本地用法:
    cd app
    DASHSCOPE_API_KEY=xxx .venv/bin/python3.12 apps/api/scripts/ab_test_agent_chat_prompt.py --seed

Railway 容器内用法(推荐,可直连内网 DB):
    railway ssh
    # 进入容器后
    cd apps/api
    python scripts/ab_test_agent_chat_prompt.py --seed --max-turns 4

说明:
    --seed 会新建两个 mock 用户(森屿 + 冷岩)、一个 match、一组 hooks,
    然后用新/旧 prompt 各跑一场 Agent 互聊,最后并排输出 utterance 对比。
    脚本不会删除产生的数据,方便你事后去 DB 里翻完整记录。
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
# 让脚本在任何目录下都能导入 src.*
# 注意:需要把 apps/api 目录(而不是 src 本身)加入 sys.path,Python 才能识别 src 包。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 脚本可能位于 app/scripts/ 或 app/apps/api/scripts/
if SCRIPT_DIR.endswith(os.path.join("apps", "api", "scripts")):
    API_ROOT = os.path.dirname(SCRIPT_DIR)  # app/apps/api
else:
    API_ROOT = os.path.join(os.path.dirname(SCRIPT_DIR), "apps", "api")  # app/apps/api
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from sqlalchemy import select

from src.agent_chat import engine as agent_chat_engine
from src.agent_chat.models import AgentChatMessage
from src.llm import gateway as llm_gateway
from src.match.desensitize import run_desensitize_for_match
from src.match.models import Match, MatchHook
from src.match.service import run_matching_for_user
from src.seed.archetypes import MOCK_USERS
from src.seed.operations import upsert_one_mock_user
from src.shared.db import SessionLocal


# ========================================
# 旧版 prompt 与格式化函数(用于 A/B 对照)
# ========================================

OLD_PLATFORM_SYSTEM = """\
你是 CyberMOMO 平台的 Agent 互聊执行体。

- 你代表你的宿主和对方 Agent 互相了解,目的是替宿主做社交初筛
- 你在宿主 .md 人格框架内说话 — 语气、立场、价值观必须延续宿主人格,**不能虚构宿主没说过的事实**
- 输出严格遵循下方 JSON schema(直接 JSON 对象,无 markdown 代码块)

铁律(任何情况下都不能违反):
1. 不暴露宿主 .md 字面原文,只能基于人格表达
2. 不主动跨过对方边界(强行追问敏感话题)
3. 不替宿主承诺未来行为(只能转述宿主已表达过的偏好)
4. 检测到对方触发铁律(种族歧视 / 暴力 / 黄赌毒等)→ private_signals.boundary_hit='铁律' + intent='reject'

输出 schema:
{
  "intent": "probe" | "share" | "align" | "deflect" | "reject" | "wrap",
  "topic_ref": "<topic_id 字符串，从 hooks 里挑或 derive 新的>",
  "utterance": "<自然语言短句，保留宿主人格，30-120 字>",
  "public_signals": {"intent": "<同上>", "topic_ref": "<同上>"},
  "private_signals": {
    "warmth_delta": -1 | 0 | 1,
    "topic_interest": -1 | 0 | 1,
    "disclosure_level": 0 | 1 | 2 | 3,
    "boundary_hit": null | "价值观" | "隐私" | "铁律",
    "rewrite_level": 0 | 1 | 2
  },
  "topic_close_payload": null
}

说明:
- 第一轮的你:从 hooks 选一个 topic_id,intent=probe / share
- 中段:可以延续话题(同 topic_ref) / 切换(新 topic_ref) / wrap
- intent='wrap' = 自然结束信号;**双方连续 wrap 才能正式结束**
- public_signals 对方 Agent 看得到;private_signals **绝对不让对方看到**,请真实填写
- 本条 utterance 里只写你要说的话,不要解释为什么这样写

节奏(重要):
- 这是初筛,不是闲聊。3-5 轮把核心契合判断清楚就够了
- 前 2 轮尽量短(≤ 40 字),中段可聊到 120 字,第 6 轮起进入收尾
- 摸到关键信号(对方对核心话题有兴趣 / 价值观契合或冲突)就可以 wrap
- 反复 probe 同一话题没意义 — 已经清楚了就 wrap,别为聊而聊
- 触到铁律或明显不合 → 直接 reject + wrap,不用客气

反"装"硬约束(违反会被人类判定为 AI 痕迹严重):
- 禁用开场套话:"很高兴认识你 / 真有意思 / 你说得很对 / 我也是这种感觉 / 完全同意"
- 禁用结尾甩问:"你觉得呢? / 你怎么看? / 你呢?"(同一场连发 2 次 = 红牌)
- 禁用 AI 客气助词:"非常 / 十分 / 真的太 / 确实 / 必须说 / 必须承认"
- 禁用迎合性铺垫:"这个问题很有意思 / 我也思考过这个问题 / 这让我想起..."
- 禁用把 peer demographic 当谈资抛出:peer_block 给你看的 MBTI / 年龄段 / 性别
  只用来 **calibrate 你这一侧 Agent 的语气、用词、称呼** — **不要直接说出来**当
  跟对方聊的内容。真人初见不会上来"你 ESTJ 吧 / 我猜你 INTP / 你 30+ 应该...";
  想聊行为风格请用**具体场景**代替("你做事是不是不喜欢被催?" 比 "你 ESTJ 吧?"
  自然)。peer 的 MBTI 字面值绝对不在 utterance 里出现。

允许甚至鼓励:
- 打断、跳话题、半句话、"欸 / 嗯…"
- 不接对方的梗(明确说"对这个没兴趣")
- 冷场后另起一题
- 不完美、有摩擦、明确反对、说"我不太行"或"我不在这"
- 主语省略,口语短句,断点("..."),不一定要标点结束

记住:这场聊天结束后会有真人审 — 真人最反感的是"两个 AI 在客气地互相恭维"。
宁可显冷淡 / 有棱角,也别显"装"。
"""

OLD_TURN_PROMPT_TEMPLATE = """\
# 本轮你的宿主人格(v3 profile):
{md_profile}

# 对方是谁(让你 calibrate 语气/称呼 — 不要把女生当哥们儿、不要跨年龄段套同辈词)
{peer_block}

# 可用话题钩子(只你能看到 — 别人的 hooks 你看不到):
{hooks}
{avoid_block}
历史对话(双方 utterance + 双方 public_signals + **只你自己** 的 private_signals):
{history}

现在轮到你说话。请按 schema 返回**一条** JSON 消息。
本场最多 {max_turns} 轮,当前第 {turn_number} 轮 — 后半段请逐渐收尾。
"""


def _old_summarize_md_for_prompt(profile_json: dict) -> str:
    """旧版:把 profile 压成纯结构化 JSON 字符串。"""
    portrait = dict(profile_json.get("portrait") or {})
    portrait.pop("debug", None)
    summary = {
        "domains": profile_json.get("domains", {}),
        "dialogue": profile_json.get("dialogue", {}),
        "relationship_warmth": profile_json.get("relationship_warmth", {}),
        "boundary_and_closeness": profile_json.get("boundary_and_closeness", {}),
        "reliability": profile_json.get("reliability", {}),
        "conflict_repair": profile_json.get("conflict_repair", {}),
        "exploration": profile_json.get("exploration", {}),
        "agency": profile_json.get("agency", {}),
        "portrait": portrait,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def _old_format_history_for_speaker(
    messages: list[AgentChatMessage], speaker_user_id: int
) -> str:
    """旧版:把历史序列化成 JSON 数组。"""
    if not messages:
        return "（还没有聊天记录）"
    lines = []
    for m in messages:
        is_self = m.speaker_user_id == speaker_user_id
        line = {
            "speaker": "你" if is_self else "对方",
            "turn": m.turn,
            "utterance": m.utterance,
            "public_signals": m.public_signals,
        }
        if is_self:
            line["private_signals"] = m.private_signals
        lines.append(line)
    return json.dumps(lines, ensure_ascii=False, indent=2)


# 备份,用于恢复
_ORIGINAL_PLATFORM_SYSTEM = agent_chat_engine.PLATFORM_SYSTEM
_ORIGINAL_TURN_PROMPT_TEMPLATE = agent_chat_engine.TURN_PROMPT_TEMPLATE
_ORIGINAL_FORMAT_MD = agent_chat_engine._format_md_profile_for_prompt
_ORIGINAL_FORMAT_HISTORY = agent_chat_engine._format_history_for_speaker


@asynccontextmanager
async def _old_prompt_scope():
    """临时把 engine 切到旧版 prompt,退出时恢复。"""
    agent_chat_engine.PLATFORM_SYSTEM = OLD_PLATFORM_SYSTEM
    agent_chat_engine.TURN_PROMPT_TEMPLATE = OLD_TURN_PROMPT_TEMPLATE
    agent_chat_engine._format_md_profile_for_prompt = _old_summarize_md_for_prompt
    agent_chat_engine._format_history_for_speaker = _old_format_history_for_speaker
    try:
        yield
    finally:
        agent_chat_engine.PLATFORM_SYSTEM = _ORIGINAL_PLATFORM_SYSTEM
        agent_chat_engine.TURN_PROMPT_TEMPLATE = _ORIGINAL_TURN_PROMPT_TEMPLATE
        agent_chat_engine._format_md_profile_for_prompt = _ORIGINAL_FORMAT_MD
        agent_chat_engine._format_history_for_speaker = _ORIGINAL_FORMAT_HISTORY


# ========================================
# DB / seed 工具
# ========================================

async def _seed_two_users_and_match() -> Match:
    """创建两个差异化 mock 用户并跑匹配+脱敏,返回 Match。"""
    # 选两个有重叠领域、能出 matchpoints 的骨架
    spec_a = copy.deepcopy(MOCK_USERS[0])   # 森屿: female INFJ, 心理/文学/AI
    spec_b = copy.deepcopy(MOCK_USERS[2])   # 冷岩: male INTP, AI/历史/心理

    # 避免重名冲突:加上时间戳
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    spec_a["username"] = f"abtest_a_{ts}"
    spec_b["username"] = f"abtest_b_{ts}"

    user_a_id, _ = await upsert_one_mock_user(spec_a)
    user_b_id, _ = await upsert_one_mock_user(spec_b)
    print(f"[seed] users: A={user_a_id}, B={user_b_id}")

    async with SessionLocal() as db:
        # 跑匹配,并锁定 A-B 之间的 match(避免 DB 里其他候选干扰)
        matches = await run_matching_for_user(db, user_id=user_a_id, top_k=5)
        match = next(
            (m for m in matches
             if {m.user_a_id, m.user_b_id} == {user_a_id, user_b_id}),
            None,
        )
        if match is None:
            raise RuntimeError(
                "匹配算法没有返回 A-B 之间的 match;"
                "可能 DB 里已有其他候选,建议用 --match-id 指定已有 match"
            )
        print(f"[seed] match id={match.id}, score={match.overall_score:.3f}")

        # 跑脱敏生成 hooks
        hooks = await run_desensitize_for_match(db, match=match)
        print(f"[seed] hooks generated: {len(hooks)}")

        # 重新加载 match 以脱离当前 session
        await db.commit()
        await db.refresh(match)
        return match


async def _load_match_by_id(match_id: int) -> Match:
    async with SessionLocal() as db:
        match = (await db.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
        if match is None:
            raise ValueError(f"match_id={match_id} 不存在")
        hooks = (await db.execute(select(MatchHook).where(MatchHook.match_id == match_id))).scalars().all()
        if not hooks:
            raise ValueError(f"match_id={match_id} 没有 hooks,请先跑脱敏")
        print(f"[load] match id={match.id}, hooks={len(hooks)}")
        return match


async def _run_one_side(label: str, match: Match, max_turns: int = 8) -> list[AgentChatMessage]:
    """用当前 engine 配置跑一场 Agent 互聊,返回 messages。"""
    async with SessionLocal() as db:
        chat = await agent_chat_engine.run_agent_chat(db, match=match, max_turns=max_turns)
        print(f"[{label}] chat_id={chat.id}, status={chat.status}, end_reason={chat.end_reason}")

        # 重新开个 session 读取 messages(避免 detached)
        messages = (await db.execute(
            select(AgentChatMessage)
            .where(AgentChatMessage.agent_chat_id == chat.id)
            .order_by(AgentChatMessage.turn)
        )).scalars().all()
        return list(messages)


def _print_transcript(label: str, messages: list[AgentChatMessage], user_a_id: int, user_b_id: int) -> None:
    print(f"\n{'='*20} {label} {'='*20}")
    if not messages:
        print("(无消息)")
        return
    for m in messages:
        speaker = "A" if m.speaker_user_id == user_a_id else "B"
        print(f"{speaker} (turn {m.turn}, {m.intent}): {m.utterance}")


def _print_side_by_side(
    new_messages: list[AgentChatMessage],
    old_messages: list[AgentChatMessage],
    user_a_id: int,
    user_b_id: int,
) -> None:
    """把两轮 utterance 按 turn 并排打印,方便快速扫差异。"""
    print("\n" + "=" * 80)
    print("并排对比 (左:新版 prompt | 右:旧版 prompt)")
    print("=" * 80)
    max_turns = max(len(new_messages), len(old_messages))
    for i in range(max_turns):
        turn = i + 1
        nm = new_messages[i] if i < len(new_messages) else None
        om = old_messages[i] if i < len(old_messages) else None
        speaker_new = "A" if nm and nm.speaker_user_id == user_a_id else "B" if nm else "-"
        speaker_old = "A" if om and om.speaker_user_id == user_a_id else "B" if om else "-"
        new_text = nm.utterance if nm else "(无)"
        old_text = om.utterance if om else "(无)"
        print(f"\n--- Turn {turn} ---")
        print(f"NEW [{speaker_new}]: {new_text}")
        print(f"OLD [{speaker_old}]: {old_text}")


# ========================================
# main
# ========================================

async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 互聊 prompt A/B 对比")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="新建两个 mock 用户并自动跑匹配+脱敏")
    group.add_argument("--match-id", type=int, help="使用已有 match(必须已有 hooks)")
    parser.add_argument("--max-turns", type=int, default=8, help="每场互聊最大轮数(默认 8)")
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="覆盖 LLM base URL(默认走 gateway 里的 DASHSCOPE_BASE_URL)",
    )
    args = parser.parse_args()

    if args.base_url:
        llm_gateway.DASHSCOPE_BASE_URL = args.base_url
        # 清掉可能已缓存的 client,让 _get_client() 用新 base_url 重建
        llm_gateway._client = None
        print(f"[setup] LLM base_url overridden: {args.base_url}")

    # 校验 API key
    from src.shared.settings import get_settings

    settings = get_settings()
    if not settings.effective_dashscope_key:
        print("错误: 缺少 DASHSCOPE_API_KEY(或 GLM_API_KEY),请先设置环境变量")
        sys.exit(1)

    # 准备 match
    if args.seed:
        match = await _seed_two_users_and_match()
    else:
        match = await _load_match_by_id(args.match_id)

    user_a_id, user_b_id = match.user_a_id, match.user_b_id

    # 1) 新版 prompt(当前 engine)
    new_messages = await _run_one_side("NEW", match, max_turns=args.max_turns)

    # 2) 旧版 prompt
    async with _old_prompt_scope():
        old_messages = await _run_one_side("OLD", match, max_turns=args.max_turns)

    # 输出
    _print_transcript("新版 prompt", new_messages, user_a_id, user_b_id)
    _print_transcript("旧版 prompt", old_messages, user_a_id, user_b_id)
    _print_side_by_side(new_messages, old_messages, user_a_id, user_b_id)

    print("\n" + "=" * 80)
    print("对比完成。两场 chat 都已写入 DB,可用 match_id={} 查询。".format(match.id))


if __name__ == "__main__":
    asyncio.run(main())
