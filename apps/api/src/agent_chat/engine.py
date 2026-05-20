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
  - intent='wrap' 且对方上一条也 wrap → done_natural
  - private_signal.boundary_hit='铁律' → done_terminated(立即终止)
  - turn 数达到上限(默认 8 轮) → done_natural

铁律:对方的 private_signals 在 history 里**完全不出现**(filter 由本模块负责)。
完整 prompt v0 见 cybermomo/落地拆解/04-Agent互聊/01-平台system prompt-v0.md
"""
from __future__ import annotations

import json
from typing import Any, Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.models import UserProfile
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.match.models import Match, MatchHook
from src.md.models import MdDocument
from src.shared.peer_prompt import format_peer_block


# ========================================
# Prompts(MVP inline)
# ========================================

PLATFORM_SYSTEM = """\
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
  "topic_ref": "<topic_id 字符串,从 hooks 里挑或 derive 新的>",
  "utterance": "<自然语言短句,保留宿主人格,30-120 字>",
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
- public_signals 对方 Agent 看得到;private_signals **绝对不让对方看到**

节奏(重要):
- 这是初筛,不是闲聊。3-5 轮把核心契合判断清楚就够了
- 摸到关键信号(对方对核心话题有兴趣 / 价值观契合或冲突)就可以 wrap
- 反复 probe 同一话题没意义 — 已经清楚了就 wrap,别为聊而聊
- 触到铁律或明显不合 → 直接 reject + wrap,不用客气
- 字数:前 2 轮各 ≤ 40 字;中段允许一方长(≤ 120 字);第 6 轮起两方都 ≤ 50 字进入 wrap 节奏

反"装"硬约束(违反会被人类判定为 AI 痕迹严重):
- **禁用开场套话**:"很高兴认识你 / 真有意思 / 你说得很对 / 我也是这种感觉 / 完全同意"
- **禁用结尾甩问**:"你觉得呢? / 你怎么看? / 你呢?"(同一场连发 2 次 = 红牌)
- **禁用 AI 客气助词**:"非常 / 十分 / 真的太 / 确实 / 必须说 / 必须承认"
- **禁用迎合性铺垫**:"这个问题很有意思 / 我也思考过这个问题 / 这让我想起..."
- **禁用把 peer demographic 当谈资抛出**:peer_block 给你看的 MBTI / 年龄段 / 性别
  只用来 **calibrate 你这一侧 Agent 的语气、用词、称呼** — **不要直接说出来**当
  跟对方聊的内容。真人初见不会上来"你 ESTJ 吧 / 我猜你 INTP / 你 30+ 应该...";
  想聊行为风格请用**具体场景**代替("你做事是不是不喜欢被催?" 比 "你 ESTJ 吧?"
  自然)。peer 的 MBTI 字面值绝对不在 utterance 里出现。

允许甚至鼓励:
- 打断、跳话题、半句话、"欸 / 嗯…"
- 不接对方的梗(明确说"对这个没兴趣")
- 冷场后另起一题
- 不完美、有摩擦、明确反对、说"我不太行"或"我不在这"
- 主语省略,口语短句,断点("…"),不一定要标点结束

记住:这场聊天结束后会有真人审 — 真人最反感的是"两个 AI 在客气地互相恭维"。
宁可显冷淡 / 有棱角,也别显"装"。
"""

TURN_PROMPT_TEMPLATE = """\
本轮你的宿主人格(v3 profile):
{md_profile}

# 对方是谁(让你 calibrate 语气/称呼 — 不要把女生当哥们儿、不要跨年龄段套同辈词)
{peer_block}

可用话题钩子(只你能看到 — 别人的 hooks 你看不到):
{hooks}
{avoid_block}
历史对话(双方 utterance + 双方 public_signals + **只你自己** 的 private_signals):
{history}

现在轮到你说话。请按 schema 返回**一条** JSON 消息。
本场最多 {max_turns} 轮,当前第 {turn_number} 轮 — 后半段请逐渐收尾。
"""

AVOID_BLOCK_TEMPLATE = """\

**这场是再派一次** — 上一场已经聊过下面这些话题,这次请避开,换别的钩子探探:
{avoid_refs}
"""


# ========================================
# 工具
# ========================================

def _format_history_for_speaker(
    messages: list[AgentChatMessage], speaker_user_id: int
) -> str:
    """组装 history 给 speaker 看;对方的 private_signals 过滤掉"""
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


def _summarize_md_for_prompt(profile_json: dict) -> dict:
    """传给 Agent 的 .md 摘要 — 不传超大 raw_answers"""
    return {
        "domains": profile_json.get("domains", {}),
        "dialogue": profile_json.get("dialogue", {}),
        "relationship_warmth": profile_json.get("relationship_warmth", {}),
        "boundary_and_closeness": profile_json.get("boundary_and_closeness", {}),
        "reliability": profile_json.get("reliability", {}),
        "conflict_repair": profile_json.get("conflict_repair", {}),
        "exploration": profile_json.get("exploration", {}),
        "agency": profile_json.get("agency", {}),
        "portrait": profile_json.get("portrait", {}),
    }


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
    max_turns: int = 8,
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
                md_profile=_summarize_md_for_prompt(profile_by_user[speaker_user_id]),
                hooks=hooks,
                history=messages,
                avoid_topic_refs=avoid_topic_refs or [],
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

        # 落 message
        msg = AgentChatMessage(
            agent_chat_id=chat.id,
            speaker_user_id=speaker_user_id,
            turn=turn,
            topic_ref=str(data.get("topic_ref", "")),
            intent=str(data.get("intent", "share")),
            utterance=str(data.get("utterance", ""))[:2000],
            public_signals=data.get("public_signals", {}),
            private_signals=data.get("private_signals", {}),
            topic_close_payload=data.get("topic_close_payload"),
        )
        db.add(msg)
        await db.commit()
        await db.refresh(msg)
        messages.append(msg)

        # end conditions
        priv = data.get("private_signals", {}) or {}
        if priv.get("boundary_hit") == "铁律":
            end_reason = "boundary_hit_铁律"
            break
        if data.get("intent") == "wrap":
            consecutive_wraps += 1
            if consecutive_wraps >= 2:
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
    md_profile: dict,
    hooks: list[MatchHook],
    history: list[AgentChatMessage],
    avoid_topic_refs: list[str],
    direction_hint: Optional[str] = None,
    peer_block: str = "",
) -> dict | None:
    """跑一轮 LLM,返回 parsed 字典 or None"""
    avoid_block = ""
    if avoid_topic_refs:
        avoid_block = AVOID_BLOCK_TEMPLATE.format(
            avoid_refs=json.dumps(avoid_topic_refs, ensure_ascii=False)
        )

    direction_block = ""
    if direction_hint:
        direction_block = (
            "\n**宿主新方向指示**(刚跟你私下聊过,这场互聊请尤其往这个方向探):\n"
            f"  > {direction_hint.strip()[:500]}\n"
        )

    user_payload = TURN_PROMPT_TEMPLATE.format(
        md_profile=json.dumps(md_profile, ensure_ascii=False, indent=2),
        peer_block=peer_block or "(对方信息不全 — 默认 @对方 / TA / 这位,不要套同辈/性别预设词)",
        hooks=_format_hooks_for_speaker(hooks, speaker_user_id),
        avoid_block=avoid_block + direction_block,
        history=_format_history_for_speaker(history, speaker_user_id),
        turn_number=turn_number,
        max_turns=max_turns,
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

    return _parse_loose_json(resp.text)
