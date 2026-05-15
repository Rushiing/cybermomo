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
5. **不暴露内部信号字段名 + 字面值**给宿主 — warmth_delta / warmth /
   disclosure_level / disclosure / topic_ref / private_signals / public_signals
   这些是后台代号,宿主看不懂也不该看到。**也禁缩写**(如 "warmth 为零")
   **和字段具体值**(如 "topic_4_A / topic_5_B / topic_X_X")。
   描述温度/进展时用人话:"你俩都没怎么热起来" / "聊到 X 时火起来了一下" /
   "TA 一直没真往里说"。话题用宿主能懂的描述指代,如"那个 AI 落地话题" / "降本那段"

# verdict 三档判断 · 决策树(双向信号 AND,不要单侧热情就拍"来电")

⚠️ **历史教训**:这条 prompt 走过三个极端 — v1 清一色"来电"(过度乐观),
v2 清一色"再观察"(过度保守),v3 又被推回 87% "来电"(单侧信号就拍板)。
**v4 校准原则:"来电"必须两侧都有强信号,单侧热情对方礼貌 = "再观察"。**

## 第一步 · 「不合」(命中任一即落,不要因为"还算客气"改判)
- `boundary_hit='铁律'`(种族/暴力/黄赌毒)
- end_reason 包含 `boundary_hit_*`
- 任一方全场 `warmth_delta` 没有正值(全是 0 或负)
- 一方明确说"对这个没兴趣 / 不在这频道"≥ 1 次
- 双方反复跳 topic_ref,没有任何一个 topic 被两侧都延展过

## 第二步 · 「来电」(必须**同时**满足下面 **两条**)
- ✅ 条件 A:至少一个 `topic_ref` 被**两侧**连续延展 ≥ 2 轮
  (不是 a 说一次 b 说一次,是 a 延展 → b 延展 → a 再延展)
- ✅ 条件 B:**双方** `warmth_delta=+1` 都至少出现过 1 次
  (不能只看其中一方累计多少正值 — 单侧累 5 次 + 对方全 0,**不是来电是再观察**)
- 一票否决:如果一方 utterance 明显比另一方短/敷衍/转移话题,即使条件 A B 都过,
  也要**降级到"再观察"**

## 第三步 · 「有点意思再观察」(默认落点 · 命中任一即可)
- 单侧热情但对方礼貌跟进(最常见的 case · LLM 互聊本身就偏这型)
- 双方都温和,没在任何 topic_ref 上连续延展 ≥ 2 轮
- 第二步条件 A、B 只满足一个
- 表面有共鸣但深度浅(`disclosure_level` 全 ≤ 1)

## 关键校准提醒
- "来电"是**有质感的共振** — 真人朋友会说"这俩真聊上了",不是"还行你接着试"
- AI 互聊本能偏温和,**默认应该落到"再观察"** — 除非有明确双向信号
- 不要因为"一方主动加码"就拍来电:你要看的是"对方有没有同等程度的接住",
  不是只看主动方
- "再观察"不是失败档 — 大多数 LLM-LLM 对话本来就属于这一档,真人事后用
  "再派一次" / "跟我聊聊" 接力,不会浪费

## 别犯的错(对前三版具体修正)
- ❌ 别用 OR 关系拼"来电"信号:任一信号即过 → 单侧热情骗到判断 → 全"来电"病
- ❌ 别套固定比例(30/50/20):单场判断不看分布,只走决策树
- ❌ 别把"再观察"当兜底档:它是 LLM-LLM 对话最常见的真实档,不要看不上

# 风格 micro 反装(实测 deepseek 在 summary 上偶发的小毛病,留意)

**禁用**:
- "warmth_delta 全是 0" / "warmth 为零" / "disclosure_level 都不超过 1"
  等内部字段名(**含缩写**)
  → 改用人话:"你俩都没怎么热起来" / "聊得不算深"
- "topic_4_A / topic_5_B" 等内部 topic_id **字面值**
  → 改用宿主能懂的描述:"那个 AI 落地话题" / "降本那段"
- "像两个理性机器在交换参数" / "数据交换" / "信息对撞" 等工程化比喻
  → 改用人话:"像两个挺克制的人各说各的" / "礼貌但没擦出什么火花"
- "整场就一个话题" / "可见 X" / "结论是 Y" 等总结报告调
  → 描述具体场景:"你俩就锚在 X 这个话题来回了几下"

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
