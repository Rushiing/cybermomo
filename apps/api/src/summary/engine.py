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

# verdict 分布参考(关键 — 上一版几乎清一色"来电",这次校准)
看完一场互聊后,你的判断要落在哪一档,大致比例如下(不强制配额,但**别默认偏正面**):
- **来电**(约 30%):双方在同一话题里主动延展 ≥ 2 次,出现真实兴奋 / 共振 / 抢话 / 主动加码的信号;一两个礼貌"对的对的"不算
- **有点意思再观察**(约 50%):有零星共鸣点但没深聊,或一方明显主导一方礼貌跟进,需要换方向再派一次确认
- **不合**(约 20%):节奏 / 话题不在一个频道,对方不接梗、或价值观/边界明显错位、或触铁律

判断锚:
- "礼貌性回应"不是来电 — 短答、转移话题、客气敷衍都不算
- 看 private_signals 的 warmth_delta / topic_interest 走势,光看 utterance 字面会被"AI 互捧"骗
- 如果一场只跑了 3-4 轮就 wrap,大概率是"再观察",别给"来电"
- 触铁律 / boundary_hit 直接走"不合"

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
