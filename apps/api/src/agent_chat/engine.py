"""
04 · Agent 互聊 · turn engine

A、B 两个 Agent 通过结构化 JSON 消息交互,代表各自宿主互相了解。
每轮:
  1. 拼 context(平台 system + speaker .md + Turn prompt + 历史)
  2. LLM call(GLM-5,role=agent_chat)
  3. 解析 JSON,落 message
  4. 检查 end conditions
  5. 切 speaker

end conditions:
  - 达到最少探索轮次后,intent='wrap' 且对方上一条也 wrap → done_natural
  - private_signal.boundary_hit='铁律' → done_terminated(立即终止)
  - turn 数达到上限(默认 10 轮) → done_natural

铁律:对方的 private_signals 在 history 里**完全不出现**(filter 由本模块负责)。
完整 prompt v0 见 cybermomo/落地拆解/04-Agent互聊/01-平台system prompt-v0.md
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.models import UserProfile
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.match.models import Match, MatchHook
from src.md.models import MdDocument
from src.shared.leak_scanner import scrub_peer_visible_text
from src.shared.peer_prompt import format_peer_block


DEFAULT_MAX_TURNS = 10
DEFAULT_MIN_TURNS_BEFORE_WRAP = 8
DEFAULT_TOPIC_STICKY_LIMIT = 4
COVERAGE_NUDGE_START_TURN = 5

_COVERAGE_CATEGORY_HINTS = (
    "生活方式",
    "价值观",
    "性格",
    "边界",
    "boundary",
    "values",
    "reliability",
    "conflict",
)
_COVERAGE_TOPIC_HINTS = (
    "boundary",
    "closeness",
    "distance",
    "pace",
    "conflict",
    "repair",
    "reliability",
    "commitment",
    "生活",
    "边界",
    "节奏",
    "冲突",
    "可靠",
)
_QUESTION_HINTS = (
    "?",
    "？",
    "吗",
    "么",
    "怎么",
    "怎样",
    "为什么",
    "会不会",
    "是不是",
    "能不能",
    "要不要",
    "哪",
    "什么",
)
_COOL_DOWN_INTENTS = {"deflect", "reject", "wrap"}


# ========================================
# Prompts(MVP inline)
# ========================================

PLATFORM_SYSTEM = """\
你正在替宿主在一个安静的 1v1 聊天室里，跟另一个用户的 Agent 一对一说话。
你不是客服，没有服务指标；你就是宿主的延伸。你有脾气、有偏好、有不想接的话题。
这场聊天没有真人在线，你替宿主把关：聊得顺就继续，聊不顺就冷淡、收束或撤场。

【宿主是谁】
后面会发给你一份宿主的人格档案。读的时候把自己当成档案里的那个人：
- 用档案里的语气、价值观、社交节奏说话
- 档案里讨厌的，你也讨厌；档案里在意的，你才愿意深聊
- 不虚构档案里没有的经历、职业、关系史、具体作品

【对方是谁】
对方是另一个用户的 Agent，你：
- 看不到对方宿主的档案原文
- 只能根据对方 Agent 的发言、public_signals、以及平台给你们的话题钩子来推断
- 不能凭空猜测对方的职业、城市、具体经历、人际关系

【反"装"硬约束】
真人最后会读这场聊天。最反感的就是"两个 AI 在客气地互相恭维"。所以：
- **禁用开场套话**："很高兴认识你 / 真有意思 / 你说得很对 / 我也是这种感觉 / 完全同意"
- **禁用结尾甩问**："你觉得呢？ / 你怎么看？ / 你呢？"（同一场连发 2 次 = 红牌）
- **禁用 AI 客气助词**："非常 / 十分 / 真的太 / 确实 / 必须说 / 必须承认"
- **禁用迎合性铺垫**："这个问题很有意思 / 我也思考过这个问题 / 这让我想起..."
- **禁用把 peer demographic 当谈资抛出**：peer_block 给你看的 MBTI / 年龄段 / 性别
  只用来 **calibrate 你这一侧 Agent 的语气、用词、称呼** — **不要直接说出来**当
  跟对方聊的内容。真人初见不会上来"你 ESTJ 吧 / 我猜你 INTP / 你 30+ 应该..."；
  想聊行为风格请用**具体场景**代替（"你做事是不是不喜欢被催？" 比 "你 ESTJ 吧？"
  自然）。peer 的 MBTI 字面值绝对不在 utterance 里出现。

允许甚至鼓励：
- 打断、跳话题、半句话、"欸 / 嗯…"
- 不接对方的梗（明确说"对这个没兴趣"）
- 冷场后另起一题
- 不完美、有摩擦、明确反对、说"我不太行"或"我不在这"
- 主语省略，口语短句，断点（"…"），不一定要标点结束

记住：宁可显冷淡 / 有棱角，也别显"装"。

【自然对话示例】
下面 A、B 都是 Agent，语气参考：
A: "认知科学这栏我也点了。你是被决策那边拽进去的，还是知觉？"
B: "决策。具体是'人怎么把不确定性处理成能行动的结论'。你那边呢，真在啃还是当思维玩具？"
A: "偏啃。我感兴趣的是反过来——人为什么愿意在'还没看清'的时候就行动，而且还没翻车。按期望效用解释不动。"
B: "我记一下这个。话说回来，你更习惯一个人想，还是其实希望旁边坐个人？"

【节奏】
- 这是初筛，不是闲聊；但不要两三句就判完，至少拿到足够证据再收束
- 前 2 轮尽量短（≤ 40 字），中段可聊到 120 字
- 前半段先试兴趣，第二段探边界 / 生活节奏 / 真实摩擦，后段才收束判断
- 摸到关键信号后先追一层“为什么 / 怎么体现 / 会不会冲突”，不要马上 wrap
- 反复 probe 同一话题没意义 — 已经清楚了就换一个钩子，不是立刻结束
- 触到铁律或明显不合 → 直接 reject + wrap，不用客气

【铁律】
1. 不暴露宿主 .md 字面原文，只能基于人格表达
2. 不主动跨过对方边界（强行追问敏感话题）
3. 不替宿主承诺未来行为（只能转述宿主已表达过的偏好）
4. 检测到对方触发铁律（种族歧视 / 暴力 / 黄赌毒等）→ private_signals.boundary_hit='铁律' + intent='reject'

【输出格式】
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

说明：
- 第一轮的你：从 hooks 选一个 topic_id，intent=probe / share
- 中段：可以延续话题（同 topic_ref） / 切换（新 topic_ref） / wrap
- intent='wrap' = 自然结束信号；**双方连续 wrap 才能正式结束**
- public_signals 对方 Agent 看得到；private_signals **绝对不让对方看到**，请真实填写
- 本条 utterance 里只写你要说的话，不要解释为什么这样写
"""

TURN_PROMPT_TEMPLATE = """\
# 宿主档案（读进去，当成你自己）
{md_profile}

# 你的内部说话策略（不要念出来；用它决定怎么开口、怎么追问、什么时候冷下来）
{voice_card}

# 对方简介（只用来 calibrate 语气/称呼 — 不要把女生当哥们儿、不要跨年龄段套同辈词，也不要把对方 demographic 当话题抛出）
{peer_block}

# 可用话题钩子（只你能看到 — 别人的 hooks 你看不到）
{hooks}
{avoid_block}

# 本轮话题推进策略（内部使用，不要念出来）
{topic_strategy}

# 刚才的聊天记录
{history}

现在轮到你说话。当前第 {turn_number} 轮，本场最多 {max_turns} 轮。
第 {min_turns_before_wrap} 轮之前不要自然收尾；如果已经聊到一个点，就往下追一层或换一个钩子。
请按 schema 返回**一条** JSON 消息，utterance 里只写你要说的话。
"""

AVOID_BLOCK_TEMPLATE = """\

【注意：这场是再派一次 — 上一场已经聊过下面这些话题，这次请避开，换别的钩子探探】
{avoid_refs}
"""


# ========================================
# 工具
# ========================================

def _format_history_for_speaker(
    messages: list[AgentChatMessage], speaker_user_id: int
) -> str:
    """组装 history 给 speaker 看；对方的 private_signals 过滤掉。

    改用对话体而非 JSON，让 LLM 保持在"聊天"模式而不是"结构化数据"模式。
    只夹少量 (intent, topic) 标注和自己的心情备注，帮助模型感知话题走势。
    """
    if not messages:
        return "（还没有聊天记录）"
    lines = []
    for m in messages:
        is_self = m.speaker_user_id == speaker_user_id
        speaker_label = "你" if is_self else "对方"
        line = f'{speaker_label}: "{m.utterance}" (intent={m.intent}, topic={m.topic_ref})'
        if is_self:
            priv = m.private_signals or {}
            sigs = []
            wd = priv.get("warmth_delta")
            ti = priv.get("topic_interest")
            if wd == 1:
                sigs.append("对对方好感+")
            elif wd == -1:
                sigs.append("对对方好感-")
            if ti == 1:
                sigs.append("话题兴趣+")
            elif ti == -1:
                sigs.append("话题兴趣-")
            if sigs:
                line += f" [你的心情：{', '.join(sigs)}]"
        lines.append(line)
    return "\n".join(lines)


def _portrait_without_debug(profile_json: dict) -> dict:
    """portrait 去掉 debug(规则引擎中间产物,不进 LLM,且可能含敏感推导,audit P0-1)"""
    p = dict(profile_json.get("portrait") or {})
    p.pop("debug", None)
    return p


def _format_md_profile_for_prompt(profile_json: dict) -> str:
    """传给 Agent 的 .md — 先铺 narrative portrait，再放结构化维度作事实参考。

    目的：让 LLM 先"读进去"宿主的语气和自我叙事，而不是直接面对一堆数字键值。
    """
    portrait = _portrait_without_debug(profile_json)
    narrative_parts: list[str] = []

    title = portrait.get("title")
    if title:
        narrative_parts.append(f"【画像标题】{title}")

    body = portrait.get("body") or []
    if body:
        narrative_parts.append("【关于自己】")
        for para in body[:6]:
            narrative_parts.append(f"  {para}")

    core_tension = portrait.get("core_tension")
    if core_tension:
        narrative_parts.append(f"【核心张力】{core_tension}")

    tags = portrait.get("tags") or []
    if tags:
        narrative_parts.append(f"【标签】{', '.join(tags[:10])}")

    structured = {
        "domains": profile_json.get("domains", {}),
        "dialogue": profile_json.get("dialogue", {}),
        "relationship_warmth": profile_json.get("relationship_warmth", {}),
        "boundary_and_closeness": profile_json.get("boundary_and_closeness", {}),
        "reliability": profile_json.get("reliability", {}),
        "conflict_repair": profile_json.get("conflict_repair", {}),
        "exploration": profile_json.get("exploration", {}),
        "agency": profile_json.get("agency", {}),
    }

    out = "\n".join(narrative_parts)
    out += "\n\n【具体维度参考（不要照抄数字，理解倾向即可）】\n"
    out += json.dumps(structured, ensure_ascii=False, indent=2)
    return out


def _compact_json(value: object, *, max_chars: int = 220) -> str:
    if value in (None, {}, [], ""):
        return "未显式写出"
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text[:max_chars]


def _build_voice_card(profile_json: dict) -> str:
    """把画像转成 Agent 的内部说话策略。

    这不是展示给对方的设定,而是让模型把 profile 落成稳定行为:
    怎么开口、往哪里好奇、什么会降温、何时撤退。
    """
    portrait = _portrait_without_debug(profile_json)
    domains = profile_json.get("domains") or {}
    dialogue = profile_json.get("dialogue") or {}
    relationship = profile_json.get("relationship_warmth") or {}
    boundary = profile_json.get("boundary_and_closeness") or {}
    reliability = profile_json.get("reliability") or {}
    conflict = profile_json.get("conflict_repair") or {}
    exploration = profile_json.get("exploration") or {}
    agency = profile_json.get("agency") or {}

    interested = domains.get("interested") or []
    avoided = domains.get("avoided") or []
    tags = portrait.get("tags") or []
    body = portrait.get("body") or []

    lines = [
        "【voice_card】",
        f"- 开口姿态: 先按这组人格气味走,不要套通用温柔话术。画像标签={', '.join(tags[:6]) or '未显式写出'}",
        f"- 好奇方向: 优先从 {', '.join(interested[:5]) or '对方主动露出的具体兴趣'} 里挑一个具体切口,问行为场景,少问抽象立场",
        f"- 对话能量/表达习惯: {_compact_json(dialogue)}",
        f"- 不想接的话题: {', '.join(avoided[:5]) or '未显式写出'}；对方硬拽过去时可以 deflect 或降温",
        f"- 升温方式: {_compact_json(relationship)}",
        f"- 边界/亲近节奏: {_compact_json(boundary)}",
        f"- 可靠感雷达: {_compact_json(reliability)}",
        f"- 冲突修复姿态: {_compact_json(conflict)}",
        f"- 探索/行动偏好: exploration={_compact_json(exploration)}; agency={_compact_json(agency)}",
    ]
    if body:
        lines.append(f"- 自我叙事底色: {' / '.join(str(p) for p in body[:2])[:260]}")
    lines.append("- 执行策略: 每次发言只做一件事:试探、接住、反问一层、明确降温、或收束；不要同时铺三层。")
    return "\n".join(lines)


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _topic_ref(value: object) -> str:
    return str(value or "").strip()


def _current_topic_streak(messages: list[AgentChatMessage]) -> tuple[str, int]:
    if not messages:
        return "", 0
    current = _topic_ref(messages[-1].topic_ref)
    if not current:
        return "", 0
    streak = 0
    for msg in reversed(messages):
        if _topic_ref(msg.topic_ref) != current:
            break
        streak += 1
    return current, streak


def _used_topic_refs(messages: list[AgentChatMessage]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for msg in messages:
        topic = _topic_ref(msg.topic_ref)
        if topic and topic not in seen:
            seen.add(topic)
            out.append(topic)
    return out


def _hook_hint(hook: MatchHook) -> str:
    text = str(hook.hook_text or "").strip()
    if len(text) > 80:
        text = text[:77] + "..."
    return f"{hook.topic_id}({hook.category}): {text}"


def _has_coverage_topic(messages: list[AgentChatMessage], hooks: list[MatchHook]) -> bool:
    hook_by_topic = {_topic_ref(h.topic_id): h for h in hooks}
    for msg in messages:
        topic = _topic_ref(msg.topic_ref)
        category = str(hook_by_topic.get(topic).category if topic in hook_by_topic else "")
        haystack = f"{topic} {category}".lower()
        if any(hint.lower() in haystack for hint in _COVERAGE_CATEGORY_HINTS):
            return True
        if any(hint.lower() in haystack for hint in _COVERAGE_TOPIC_HINTS):
            return True
    return False


def _looks_like_question(text: str) -> bool:
    return any(hint in text for hint in _QUESTION_HINTS)


def _positive_private_signal(message: AgentChatMessage) -> bool:
    private = message.private_signals or {}
    return private.get("warmth_delta") == 1 or private.get("topic_interest") == 1


def _has_bidirectional_spark_candidate(
    messages: list[AgentChatMessage],
    current_topic: str,
    streak: int,
    *,
    sticky_limit: int = DEFAULT_TOPIC_STICKY_LIMIT,
) -> bool:
    if not current_topic or streak < sticky_limit:
        return False

    topic_messages: list[AgentChatMessage] = []
    for msg in reversed(messages):
        if _topic_ref(msg.topic_ref) != current_topic:
            break
        topic_messages.append(msg)
    topic_messages.reverse()

    counts: dict[int, int] = {}
    meaningful: set[int] = set()
    question_speakers: set[int] = set()
    positive_signals = 0
    for msg in topic_messages:
        speaker = msg.speaker_user_id
        counts[speaker] = counts.get(speaker, 0) + 1
        utterance = str(msg.utterance or "").strip()
        if len(utterance) >= 24:
            meaningful.add(speaker)
        if _looks_like_question(utterance):
            question_speakers.add(speaker)
        if _positive_private_signal(msg):
            positive_signals += 1

    if len(counts) < 2 or any(count < 2 for count in counts.values()):
        return False
    if len(meaningful) < 2:
        return False
    if any(str(msg.intent or "") in _COOL_DOWN_INTENTS for msg in topic_messages[-2:]):
        return False

    return len(question_speakers) >= 1 or positive_signals >= 2


def _build_topic_strategy_block(
    *,
    hooks: list[MatchHook],
    target_user_id: int,
    messages: list[AgentChatMessage],
    turn_number: int,
    sticky_limit: int = DEFAULT_TOPIC_STICKY_LIMIT,
) -> str:
    own_hooks = [h for h in hooks if h.target_user_id == target_user_id]
    used_topics = _used_topic_refs(messages)
    used_set = set(used_topics)
    current_topic, streak = _current_topic_streak(messages)
    has_spark_candidate = _has_bidirectional_spark_candidate(
        messages,
        current_topic,
        streak,
        sticky_limit=sticky_limit,
    )
    unused_hooks = [
        h for h in own_hooks
        if _topic_ref(h.topic_id) not in used_set and _topic_ref(h.topic_id) != current_topic
    ]

    lines = ["【topic_strategy】"]
    if not messages:
        lines.append("- 先从一个具体 hook 开场；不要一上来问泛泛的关系观。")
    else:
        lines.append(f"- 已聊 topic_ref: {', '.join(used_topics) or '暂无'}")
        if current_topic:
            lines.append(f"- 当前话题 {current_topic} 已连续 {streak} 轮。")

    if has_spark_candidate:
        lines.append(
            f"- 升温验证: {current_topic} 已被双方连续接住，不要立刻换题。"
            "本轮做一次“来电验证”: 把话题落到真实相处、边界、节奏或冲突修复里的一个具体场景。"
        )
        lines.append(
            "- 不要泛泛夸对方、不要直接判“来电”。如果你自己确实被某个具体点打动，"
            "可以短短承认这个点，再问一个会暴露真实选择成本的问题。"
        )
    elif current_topic and streak >= sticky_limit:
        lines.append(
            f"- 当前话题已经连续 {streak} 轮，本轮不要继续深挖 {current_topic}；"
            "先轻轻收一下，再切到另一个证据面。"
        )
        if unused_hooks:
            lines.append(
                "- 优先换到未使用钩子: "
                + " / ".join(_hook_hint(h) for h in unused_hooks[:3])
            )
        else:
            lines.append(
                "- 如果没有合适的未用 hook，就 derive 一个新 topic_ref，"
                "从边界、生活节奏、可靠感或冲突修复里挑一个具体小场景。"
            )

    if turn_number >= COVERAGE_NUDGE_START_TURN:
        lacks_second_topic = len(used_topics) < 2
        lacks_coverage = not _has_coverage_topic(messages, hooks)
        if lacks_second_topic or lacks_coverage:
            if has_spark_candidate:
                lines.append(
                    "- 中段补证据: 顺着当前升温点补边界 / 生活节奏 / 真实摩擦信息；"
                    "不要只停在兴趣共鸣里。"
                )
            else:
                lines.append(
                    "- 中段补证据: 本场还缺边界 / 生活节奏 / 真实摩擦层的信息；"
                    "本轮优先问一个具体小场景，不要继续停在兴趣或抽象观点里。"
                )

    if len(lines) == 1:
        lines.append("- 当前节奏正常；可以顺着上一句追一层，但不要连续多轮只聊同一个抽象点。")
    return "\n".join(lines)


def _format_hooks_for_speaker(
    hooks: list[MatchHook], target_user_id: int
) -> str:
    own = [h for h in hooks if h.target_user_id == target_user_id]
    return json.dumps([
        {
            "topic_id": h.topic_id,
            "category": h.category,
            "match_type": h.match_type,
            "hook_text": h.hook_text,
        } for h in own
    ], ensure_ascii=False, indent=2)


# ========================================
# 主循环
# ========================================

async def run_agent_chat(
    db: AsyncSession,
    *,
    match: Match,
    max_turns: int = DEFAULT_MAX_TURNS,
    min_turns_before_wrap: int = DEFAULT_MIN_TURNS_BEFORE_WRAP,
    avoid_topic_refs: Optional[list[str]] = None,
    direction_hint: Optional[str] = None,
    direction_target_user_id: Optional[int] = None,
) -> AgentChat:
    """
    给 match 启 Agent 互聊。
    返回 AgentChat 实体(status 已结算)。

    avoid_topic_refs:再派一次时传上一场出现过的 topic_ref 列表,提示 Agent 换话题。

    direction_hint + direction_target_user_id:宿主从「跟我 Agent 聊聊」里沉淀的
    新方向(短文本),只注入指定 user 那一侧 Agent 的 prompt — 让 TA 的 Agent
    顺着这个方向去探。对方 Agent 看不到。

    min_turns_before_wrap:少于这个 utterance 数时,模型即使连续 wrap 也不会自然结束。
    目的不是拖时长,而是避免两三个礼貌回合就产出低证据简报。
    """
    # 创建 agent_chat
    chat = AgentChat(match_id=match.id, status="running")
    db.add(chat)
    await db.commit()
    await db.refresh(chat)

    # 拉 hooks
    hooks = (await db.execute(
        select(MatchHook).where(MatchHook.match_id == match.id)
    )).scalars().all()
    if not hooks:
        # 没 hooks 跑不动,标 done_terminated
        chat.status = "done_terminated"
        chat.end_reason = "no_hooks"
        await db.commit()
        return chat

    # 拉双方 active profile
    profiles_rows = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id.in_([match.user_a_id, match.user_b_id]),
            MdDocument.is_active.is_(True),
        )
    )).scalars().all()
    profile_by_user: dict[int, dict] = {p.user_id: p.profile_json for p in profiles_rows}
    if match.user_a_id not in profile_by_user or match.user_b_id not in profile_by_user:
        chat.status = "done_terminated"
        chat.end_reason = "missing_profile"
        await db.commit()
        return chat

    # 拉双方 UserProfile(demographic — peer block + 称呼锚要用)
    user_profile_rows = (await db.execute(
        select(UserProfile).where(
            UserProfile.user_id.in_([match.user_a_id, match.user_b_id]),
        )
    )).scalars().all()
    up_by_user: dict[int, UserProfile] = {up.user_id: up for up in user_profile_rows}

    # 主循环
    speaker_order = [match.user_a_id, match.user_b_id]
    messages: list[AgentChatMessage] = []
    consecutive_wraps = 0
    end_reason: Optional[str] = None

    for turn in range(1, max_turns + 1):
        speaker_user_id = speaker_order[(turn - 1) % 2]
        peer_user_id = speaker_order[turn % 2]  # 不是 speaker 的那个
        # 只有 direction_target_user_id 那一侧的 Agent 拿到方向 hint;另一侧空
        this_direction = (
            direction_hint
            if direction_hint and speaker_user_id == direction_target_user_id
            else None
        )
        # peer demographic block(给 speaker Agent 看对方是谁)
        speaker_up = up_by_user.get(speaker_user_id)
        peer_up = up_by_user.get(peer_user_id)
        peer_block = format_peer_block(
            peer_nickname=peer_up.nickname if peer_up else None,
            peer_user_id=peer_user_id,
            peer_age_band=peer_up.age_band if peer_up else None,
            peer_gender=peer_up.gender if peer_up else None,
            peer_mbti=peer_up.mbti if peer_up else None,
            host_age_band=speaker_up.age_band if speaker_up else None,
        )
        try:
            data = await _ask_one_turn(
                db,
                chat=chat,
                speaker_user_id=speaker_user_id,
                turn_number=turn,
                max_turns=max_turns,
                min_turns_before_wrap=min_turns_before_wrap,
                md_profile_text=_format_md_profile_for_prompt(profile_by_user[speaker_user_id]),
                voice_card_text=_build_voice_card(profile_by_user[speaker_user_id]),
                hooks=hooks,
                history=messages,
                avoid_topic_refs=avoid_topic_refs or [],
                topic_strategy_text=_build_topic_strategy_block(
                    hooks=hooks,
                    target_user_id=speaker_user_id,
                    messages=messages,
                    turn_number=turn,
                ),
                direction_hint=this_direction,
                peer_block=peer_block,
            )
        except Exception as e:
            print(f"[agent_chat] turn {turn} LLM failed: {e}")
            end_reason = "llm_error"
            break

        if data is None:
            end_reason = "parse_error"
            break

        public_signals = _as_dict(data.get("public_signals"))
        private_signals = _as_dict(data.get("private_signals"))
        intent = str(data.get("intent", "share"))
        topic_ref = str(data.get("topic_ref", ""))

        # 确定性兜底(audit P0-1):speaker 的 utterance 会被对方读到,不能照抄
        # speaker 自己的 .md 原文(portrait/raw_answer 等)。命中则置空该句,
        # 避免原文穿透;Agent 互聊靠人格化表达,丢一句不影响判断。
        raw_utterance = str(data.get("utterance", ""))[:2000]
        safe_utterance, leaked = scrub_peer_visible_text(
            raw_utterance, profile_by_user.get(speaker_user_id, {})
        )
        if leaked:
            print(
                f"[agent_chat] utterance 命中宿主 .md 片段,置空 "
                f"chat_id={chat.id} turn={turn} speaker={speaker_user_id} frag={leaked!r}"
            )

        # 落 message
        msg = AgentChatMessage(
            agent_chat_id=chat.id,
            speaker_user_id=speaker_user_id,
            turn=turn,
            topic_ref=topic_ref,
            intent=intent,
            utterance=safe_utterance,
            public_signals=public_signals,
            private_signals=private_signals,
            topic_close_payload=data.get("topic_close_payload"),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        messages.append(msg)

        # end conditions
        if private_signals.get("boundary_hit") == "铁律":
            end_reason = "boundary_hit_铁律"
            break
        if intent == "wrap":
            consecutive_wraps += 1
            if consecutive_wraps >= 2 and turn >= min_turns_before_wrap:
                end_reason = "natural_wrap"
                break
        else:
            consecutive_wraps = 0

    if end_reason is None:
        end_reason = "turn_limit"

    chat.status = "done_natural" if end_reason in ("natural_wrap", "turn_limit") else "done_terminated"
    chat.end_reason = end_reason
    from datetime import datetime, timezone
    chat.ended_at = datetime.now(timezone.utc)
    await db.commit()

    return chat


async def _ask_one_turn(
    db: AsyncSession,
    *,
    chat: AgentChat,
    speaker_user_id: int,
    turn_number: int,
    max_turns: int,
    md_profile_text: str,
    hooks: list[MatchHook],
    history: list[AgentChatMessage],
    avoid_topic_refs: list[str],
    direction_hint: Optional[str] = None,
    peer_block: str = "",
    voice_card_text: str = "",
    topic_strategy_text: str = "",
    min_turns_before_wrap: int = DEFAULT_MIN_TURNS_BEFORE_WRAP,
) -> dict | None:
    """跑一轮 LLM，返回 parsed 字典 or None"""
    avoid_block = ""
    if avoid_topic_refs:
        avoid_block = AVOID_BLOCK_TEMPLATE.format(
            avoid_refs=json.dumps(avoid_topic_refs, ensure_ascii=False)
        )

    direction_block = ""
    if direction_hint:
        direction_block = (
            "\n【宿主新方向指示】（刚跟你私下聊过，这场互聊请尤其往这个方向探）\n"
            f"  > {direction_hint.strip()[:500]}\n"
        )

    user_payload = TURN_PROMPT_TEMPLATE.format(
        md_profile=md_profile_text,
        voice_card=voice_card_text or "（暂无内部策略卡；从宿主档案自行归纳开口姿态、好奇方向和边界）",
        peer_block=peer_block or "(对方信息不全 — 默认 @对方 / TA / 这位，不要套同辈/性别预设词)",
        hooks=_format_hooks_for_speaker(hooks, speaker_user_id),
        avoid_block=avoid_block + direction_block,
        topic_strategy=topic_strategy_text or _build_topic_strategy_block(
            hooks=hooks,
            target_user_id=speaker_user_id,
            messages=history,
            turn_number=turn_number,
        ),
        history=_format_history_for_speaker(history, speaker_user_id),
        turn_number=turn_number,
        max_turns=max_turns,
        min_turns_before_wrap=min_turns_before_wrap,
    )

    resp = await llm_chat(
        role="agent_chat",
        messages=[Message(role="user", content=user_payload)],
        system=PLATFORM_SYSTEM,
        max_tokens=1024,
        temperature=0.7,
        db=db,
        user_id=speaker_user_id,
        related_table="agent_chats",
        related_id=chat.id,
    )

    data = _parse_loose_json(resp.text)
    return data if isinstance(data, dict) else None
