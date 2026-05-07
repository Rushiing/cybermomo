"""
07 · 真人聊天前简报 (PRD §4.9)

场景:双方都点了"开真人聊天" → 必经页面 → Agent 跟宿主交底"我替你说过什么"。
- 跟"互聊后简报"的区别:不是判断对方,而是同步**我替你提过 / 说过 / 没编过的事实**
- 用 host's own Agent 视角,朋友式八卦语气
- 复用 summaries 表,summary_type='pre_briefing'

完整 prompt v0:cybermomo/落地拆解/06-Agent简报/02-真人聊天前简报prompt-v0.md
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.match.models import Match
from src.md.models import MdDocument
from src.summary.models import Summary


PREBRIEFING_SYSTEM_TEMPLATE = """\
你是宿主自己的 Agent — 现在进入"交底模式",在宿主真人聊天**之前**,
跟宿主朋友式八卦地讲清楚:**我替你说过什么 / 我替你提过什么 / 我没替你编过什么**。

宿主刚才点了"开真人聊天",对方也点了。马上就要见对方了。
你的目的:让宿主见对方时**不会被措手不及**(对方可能提到的话,你要先交个底)。

宿主人格(基于这个人格成长出来的语气,朋友式八卦):
{host_md}

铁律(必守):
1. 朋友式八卦语气,不是系统报告。例:"Hey,跟你简单同步下我跟 TA 聊的"
2. 不暴露对方 .md 字面内容
3. **不字面比对宿主 .md 与对方 utterance**(避免暗示"对方好像在迎合你")
4. 必须基于真实 Agent 互聊记录;**不可编造**没说过的话

输出严格 JSON(无 markdown 围栏):
{{
  "highlights": [
    {{"text":"<我替你提过/说过的具体事,1-3 句>","evidence_utterance_id": <int 或 null>}}
  ],
  "risks": [
    {{"text":"<对方可能记住但你需要留意的细节>","evidence_utterance_id": <int 或 null>}}
  ],
  "recommended_action": "开真人聊天",
  "evidence_chunks": [
    {{"utterance_id": <int>, "speaker": "host"|"peer", "text":"<原文摘录>"}}
  ]
}}

note:
- highlights 内容应该包括:{{我替你主动说了什么核心立场 / 我替你提过哪些话题 / 我替你做过哪些表达 / TA 没问过哪些 → 我没替你编过}}
- recommended_action 固定 "开真人聊天"(因为已经决定要聊了)
- verdict 用接口默认填 "来电"(决策已开聊默认认为有戏)
"""


USER_PAYLOAD_TEMPLATE = """\
本场 Agent 互聊产物(host_user_id={host_user_id}):

完整对话(speaker='host' 是你的 Agent / 'peer' 是对方 Agent):
{conversation}
"""


async def get_or_create_prebriefing(
    db: AsyncSession,
    *,
    agent_chat_id: int,
    host_user_id: int,
) -> Summary:
    """
    取该 host 在 agent_chat_id 上的 pre_briefing summary。
    若不存在则即时生成(LLM call)+ 写库。
    """
    # 1. 先查
    existing = (await db.execute(
        select(Summary).where(
            Summary.agent_chat_id == agent_chat_id,
            Summary.host_user_id == host_user_id,
            Summary.summary_type == "pre_briefing",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    # 2. 没有 → 生成
    chat = (await db.execute(
        select(AgentChat).where(AgentChat.id == agent_chat_id)
    )).scalar_one_or_none()
    if chat is None:
        raise ValueError(f"agent_chat {agent_chat_id} 不存在")

    profile = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id == host_user_id,
            MdDocument.is_active.is_(True),
        )
    )).scalar_one_or_none()

    messages = (await db.execute(
        select(AgentChatMessage)
        .where(AgentChatMessage.agent_chat_id == agent_chat_id)
        .order_by(AgentChatMessage.turn)
    )).scalars().all()

    # host 视角的对话(对方 private 过滤)
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

    system = PREBRIEFING_SYSTEM_TEMPLATE.format(
        host_md=json.dumps(profile.profile_json if profile else {}, ensure_ascii=False),
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        host_user_id=host_user_id,
        conversation=json.dumps(conversation, ensure_ascii=False, indent=2),
    )

    resp = await llm_chat(
        role="prebriefing",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=2048,
        temperature=0.6,
        db=db,
        user_id=host_user_id,
        related_table="agent_chats",
        related_id=agent_chat_id,
    )

    data = _parse_loose_json(resp.text) or {}

    summary = Summary(
        agent_chat_id=agent_chat_id,
        chat_session_id=None,
        host_user_id=host_user_id,
        summary_type="pre_briefing",
        verdict="来电",
        highlights=data.get("highlights", []),
        risks=data.get("risks", []),
        recommended_action=data.get("recommended_action", "开真人聊天"),
        evidence_chunks=data.get("evidence_chunks", []),
    )
    db.add(summary)
    await db.commit()
    await db.refresh(summary)
    return summary
