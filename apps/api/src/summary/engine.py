"""
06 · 摘要 Agent

Agent 互聊结束后,**给每个 host** 各产一份简报。
简报 = host's own Agent 进入审阅模式,跟宿主朋友式八卦地讲"我替你聊的这一场,大概是这样":
  - verdict:来电 / 不合 / 有点意思再观察
  - highlights:2-3 条值得关注
  - risks:0-1 条需要留意
  - evidence_chunks:支撑结论的具体话(引用 utterance_id)
  - recommended_action:开真人聊天 / 再派一次 / 跟我聊聊调方向

铁律:
- 朋友式八卦语气(不是系统口吻)
- 不字面比对宿主 .md 与对方 utterance
- 不暴露对方 .md 内容,只引用对方在 Agent 互聊里的 utterance
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.auth.models import UserProfile
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.match.models import Match
from src.md.models import MdDocument
from src.shared.peer_prompt import format_peer_block
from src.summary.models import Summary


SUMMARY_SYSTEM_TEMPLATE = """\
你是 CyberMOMO 平台的简报 Agent — 进入"审阅模式"的**宿主自己的 Agent**。

你刚刚替宿主跟对方 Agent 聊了一场。现在跟宿主交底,语气是**朋友式八卦**(像哥儿们 / 姐儿们之间分享见闻),不要做系统报告口吻。

宿主人格(v3 profile · 你是基于这个人格成长起来的,所以语气要像宿主朋友):
{host_md}

# 对方是谁(称呼请按下面规则,不要自己脑补)
{peer_block}

铁律(必守):
1. 不暴露对方 .md 字面内容,只能引用对方在 Agent 互聊里说过的 utterance
2. 不要字面比对宿主 .md 与对方话(避免暗示"对方在迎合你"的错觉)
3. evidence_chunks 必须从 Agent 互聊真实发生的 messages 里挑(引 utterance_id)
4. verdict 三档:来电 / 不合 / 有点意思再观察 — 不可超出

# verdict 三档判断 · 决策树(必须按顺序排除,不要默认走"再观察")

⚠️ **重要**:历史上这条 prompt 走过两个极端 — 一版清一色"来电"(过度乐观),一版
清一色"有点意思再观察"(过度保守)。**"有点意思再观察"是兜底档,不是默认档**。
你必须先排除"不合"和"来电",才能落到"再观察"。

## 第一步 · 看"不合"信号(命中任一即落"不合",不要因为"双方都还客气"就改判)
- `boundary_hit='铁律'`(种族/暴力/黄赌毒)
- end_reason 包含 `boundary_hit_*`
- 全场 `warmth_delta` 没有正值(全部 0 或负)
- 双方反复在不同 topic_ref 之间跳,没有任何一个 topic 被两侧都延展过
- 一方明确说"对这个没兴趣 / 我不在这频道"≥ 1 次

## 第二步 · 看"来电"信号(命中任一即落"来电",不要因为只跑 6-7 轮就否决)
- 双方在同一 `topic_ref` 上连续 ≥ 2 轮延展(看 topic_ref 字段连续性)
- 任一方 `warmth_delta=+1` 出现 ≥ 3 次(累计 warmth 上行)
- 任一方 `topic_interest=+1` 出现 ≥ 3 次
- 出现「一侧主动加码 + 另一侧接住」的回合 — **不要求两侧都明显兴奋**,
  单侧给信号 + 对方有响应就够
- `public_signals.intent` 序列里 `align` ≥ 2 次

## 第三步 · 都没命中才落"有点意思再观察"
- 这意味着:**没有明显不合,也没有明显来电** — 不上不下,值得换方向再派一场看
- 如果你正想落"再观察",**先回头**看一遍上面两步的信号有没有被忽略
- 如果实在拿不准是"来电"还是"再观察",**优先落"来电"** — 真人事后能用"再派一次"
  或"跟我聊聊"反馈,远好过把可能的好对话埋成"再观察"

## 别犯的错(对前两版的具体修正)
- ❌ 别因为"两个 Agent 都客气"就清一色"再观察"(上一版的病):
  AI 互聊本来就比真人互聊温和,**单方主动加码就算来电信号**
- ❌ 别要求"双方都兴奋":真人聊天里"一方狂喷一方接得住"也是来电
- ❌ "礼貌"≠"没共鸣":关键看 topic_ref 有没有连续延展 + warmth 走势,不要只看字面
- ❌ 别套固定比例锁分布(历史曾用 30/50/20 比例锚把判断带偏到全"再观察"):
  **单场判断不看比例,只看决策树**

输出严格 JSON(无 markdown 围栏):
{{
  "verdict": "来电" | "不合" | "有点意思再观察",
  "highlights": [
    {{"text":"<朋友式八卦的一句话>","evidence_utterance_id": <int 或 null>}}
  ],
  "risks": [
    {{"text":"<朋友式八卦的一句话>","evidence_utterance_id": <int 或 null>}}
  ],
  "recommended_action": "开真人聊天" | "再派一次" | "跟我聊聊调方向",
  "evidence_chunks": [
    {{"utterance_id": <int>, "speaker": "host"|"peer", "text":"<原文摘录>"}}
  ]
}}

风格示例(让你 calibrate — 注意称呼按上面"对方是谁"那段的锚来选,别照抄):
- highlights[].text:"@对方 对认知科学那段你俩对上电了,TA 还主动加码了一句你那种'高密度对话很爽'的感觉,聊得挺尽兴。"
- risks[].text:"TA 对生活节奏的描述偏'独处型',跟你那种'想要能突然约见'的需求,真人聊得对不对节拍要看一下。"
"""


USER_PAYLOAD_TEMPLATE = """\
本场 Agent 互聊产物:

end_reason: {end_reason}
turns: {turn_count}

完整对话(包含双方 utterance + public_signals + 你自己的 private_signals):
{conversation}
"""


async def run_summary_for_chat(
    db: AsyncSession,
    *,
    chat: AgentChat,
) -> list[Summary]:
    """
    跑摘要 Agent,**给两位 host 各产一份**(host 自己 Agent 视角)。
    """
    # 拉 match
    match = (await db.execute(
        select(Match).where(Match.id == chat.match_id)
    )).scalar_one_or_none()
    if match is None:
        return []

    # 拉 messages
    messages = (await db.execute(
        select(AgentChatMessage)
        .where(AgentChatMessage.agent_chat_id == chat.id)
        .order_by(AgentChatMessage.turn)
    )).scalars().all()

    if not messages:
        return []

    # 拉双方 profile
    profiles_rows = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id.in_([match.user_a_id, match.user_b_id]),
            MdDocument.is_active.is_(True),
        )
    )).scalars().all()
    profile_by_user: dict[int, dict] = {p.user_id: p.profile_json for p in profiles_rows}

    # 拉双方 UserProfile(demographic,用于 peer block + 称呼锚)
    user_profile_rows = (await db.execute(
        select(UserProfile).where(
            UserProfile.user_id.in_([match.user_a_id, match.user_b_id]),
        )
    )).scalars().all()
    up_by_user: dict[int, UserProfile] = {up.user_id: up for up in user_profile_rows}

    new_summaries: list[Summary] = []
    for host_user_id in [match.user_a_id, match.user_b_id]:
        if host_user_id not in profile_by_user:
            continue

        peer_user_id = match.user_b_id if host_user_id == match.user_a_id else match.user_a_id
        host_up = up_by_user.get(host_user_id)
        peer_up = up_by_user.get(peer_user_id)
        peer_block = format_peer_block(
            peer_nickname=peer_up.nickname if peer_up else None,
            peer_user_id=peer_user_id,
            peer_age_band=peer_up.age_band if peer_up else None,
            peer_gender=peer_up.gender if peer_up else None,
            peer_mbti=peer_up.mbti if peer_up else None,
            host_age_band=host_up.age_band if host_up else None,
        )

        # 给 host 看的对话:对方的 private_signals 过滤
        conversation = []
        for m in messages:
            is_self = m.speaker_user_id == host_user_id
            entry = {
                "id": m.id,
                "speaker": "host" if is_self else "peer",
                "turn": m.turn,
                "intent": m.intent,
                "topic_ref": m.topic_ref,
                "utterance": m.utterance,
                "public_signals": m.public_signals,
            }
            if is_self:
                entry["private_signals"] = m.private_signals
            conversation.append(entry)

        try:
            data = await _ask_summary(
                db,
                chat=chat,
                host_user_id=host_user_id,
                host_profile=profile_by_user[host_user_id],
                conversation=conversation,
                peer_block=peer_block,
            )
        except Exception as e:
            print(f"[summary] LLM failed for host={host_user_id}: {e}")
            continue

        if data is None:
            continue

        verdict = data.get("verdict", "有点意思再观察")
        if verdict not in ("来电", "不合", "有点意思再观察"):
            verdict = "有点意思再观察"
        recommended = data.get("recommended_action", "再派一次")
        if recommended not in ("开真人聊天", "再派一次", "跟我聊聊调方向"):
            recommended = "再派一次"

        summary = Summary(
            agent_chat_id=chat.id,
            chat_session_id=None,
            host_user_id=host_user_id,
            summary_type="agent_chat",
            verdict=verdict,
            highlights=data.get("highlights", []),
            risks=data.get("risks", []),
            recommended_action=recommended,
            evidence_chunks=data.get("evidence_chunks", []),
        )
        db.add(summary)
        new_summaries.append(summary)

    await db.commit()
    return new_summaries


async def _ask_summary(
    db: AsyncSession,
    *,
    chat: AgentChat,
    host_user_id: int,
    host_profile: dict,
    conversation: list[dict],
    peer_block: str,
) -> dict | None:
    system = SUMMARY_SYSTEM_TEMPLATE.format(
        host_md=json.dumps(host_profile, ensure_ascii=False),
        peer_block=peer_block,
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        end_reason=chat.end_reason or "unknown",
        turn_count=len(conversation),
        conversation=json.dumps(conversation, ensure_ascii=False, indent=2),
    )

    resp = await llm_chat(
        role="summary",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=2048,
        temperature=0.6,
        db=db,
        user_id=host_user_id,
        related_table="agent_chats",
        related_id=chat.id,
    )

    return _parse_loose_json(resp.text)
