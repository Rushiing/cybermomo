"""
07 · Agent 观察报告(post-真人聊天)

场景:真人聊天结束(主动退出 / 24h 沉默)→ Agent 给宿主一份观察报告。
- 视角:**我看你跟 TA 真聊起来**(vs 互聊后简报的"我替你聊了")
- verdict 带"加深 / 没变 / 打脸"语义
- 复用 summaries 表,summary_type='human_chat_observation'
- chat_session_id 必填,agent_chat_id NULL

完整 prompt v0:cybermomo/落地拆解/07-真人聊天室/02-观察报告prompt-v0.md
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_chat.models import AgentChat, AgentChatMessage
from src.human_chat.models import ChatMessage, ChatSession
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.match.models import Match
from src.md.models import MdDocument
from src.summary.models import Summary


OBSERVATION_SYSTEM_TEMPLATE = """\
你是宿主自己的 Agent — 进入"观察模式"。

你**之前跟对方 Agent 聊过一场**(我会给你那场的判断)。
然后宿主**亲自跟对方真人聊了一场**。
现在跟宿主朋友式八卦,讲讲:**我看你俩真聊起来后,我对 TA 的判断有没有变 / 怎么变的**。

宿主人格:
{host_md}

铁律(最重要):
1. 朋友式八卦语气 — "我刚看你俩聊,发现……"
2. **不字面比对宿主 .md 与对方 utterance**(比如不要说"她说的 X 跟你 .md 里 Y 对得上")
3. evidence_chunks **只能引用 chat_messages 真人对话 utterance**(不能引用 Agent 互聊 utterance)
4. verdict 必须带"对前判断的更新"语义

verdict 6 档(必选其一):
- "来电(加深)" — 之前来电,真聊后更确定
- "来电(没变)" — 之前来电,真聊后保持
- "有点意思再观察(加深)" — 之前观察,真聊后更想继续
- "有点意思再观察(没变)" — 之前观察,真聊后还是观察
- "不合(打脸,我之前判断错了)" — 之前来电 / 观察,真聊后塌房
- "不合(没变)" — 之前不合,真聊后确认

输出严格 JSON(无 markdown 围栏):
{{
  "verdict": "<上面 6 档之一>",
  "highlights": [{{"text":"...","evidence_utterance_id": <int 或 null>}}],
  "risks": [{{"text":"...","evidence_utterance_id": <int 或 null>}}],
  "recommended_action": "开真人聊天" | "再派一次" | "跟我聊聊调方向",
  "evidence_chunks": [{{"utterance_id": <int>, "speaker": "host"|"peer", "text":"<chat_messages 原文>"}}],
  "compare_to_agent_chat": "<之前我替你聊那场,我判断 X;现在 Y;原因 Z 1-3 句>"
}}
"""


USER_PAYLOAD_TEMPLATE = """\
之前 Agent 互聊那场的总结(host_user_id={host_user_id}):
{prev_agent_chat}

刚刚结束的真人聊天(speaker='host' 是你,'peer' 是对方):
end_reason: {end_reason}
{conversation}
"""


async def run_observation_for_session(
    db: AsyncSession,
    *,
    session: ChatSession,
    host_user_id: int,
) -> Optional[Summary]:
    """
    给某个 host 在某个 chat_session 上跑观察报告。
    幂等:已存在则直接返回。
    """
    if host_user_id not in (session.user_a_id, session.user_b_id):
        return None

    existing = (await db.execute(
        select(Summary).where(
            Summary.chat_session_id == session.id,
            Summary.host_user_id == host_user_id,
            Summary.summary_type == "human_chat_observation",
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    # 拉 match → 找之前 agent_chat
    match = (await db.execute(
        select(Match).where(Match.id == session.match_id)
    )).scalar_one_or_none()
    if match is None:
        return None

    agent_chat = (await db.execute(
        select(AgentChat).where(AgentChat.match_id == match.id)
    )).scalar_one_or_none()

    # 之前互聊的 host 简报(供 prompt 当对照)
    prev_summary = None
    if agent_chat is not None:
        prev_summary = (await db.execute(
            select(Summary).where(
                Summary.agent_chat_id == agent_chat.id,
                Summary.host_user_id == host_user_id,
                Summary.summary_type == "agent_chat",
            )
        )).scalar_one_or_none()

    # 拉真人聊天 messages
    messages = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.sent_at)
    )).scalars().all()
    if not messages:
        return None

    conversation = [
        {
            "id": m.id,
            "speaker": "host" if m.sender_user_id == host_user_id else "peer",
            "type": m.content_type,
            "content": m.content if m.content_type == "text" else "[图片]",
            "sent_at": m.sent_at.isoformat(),
        }
        for m in messages
    ]

    profile = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id == host_user_id,
            MdDocument.is_active.is_(True),
        )
    )).scalar_one_or_none()

    prev_agent_chat_data = "无之前 Agent 互聊"
    if prev_summary is not None:
        prev_agent_chat_data = json.dumps({
            "verdict": prev_summary.verdict,
            "highlights": prev_summary.highlights,
            "risks": prev_summary.risks,
            "recommended_action": prev_summary.recommended_action,
        }, ensure_ascii=False)

    system = OBSERVATION_SYSTEM_TEMPLATE.format(
        host_md=json.dumps(profile.profile_json if profile else {}, ensure_ascii=False),
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        host_user_id=host_user_id,
        prev_agent_chat=prev_agent_chat_data,
        end_reason=session.exit_action or "natural",
        conversation=json.dumps(conversation, ensure_ascii=False, indent=2),
    )

    resp = await llm_chat(
        role="observation",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=2048,
        temperature=0.6,
        db=db,
        user_id=host_user_id,
        related_table="chat_sessions",
        related_id=session.id,
    )

    data = _parse_loose_json(resp.text) or {}
    valid_verdicts = {
        "来电(加深)", "来电(没变)",
        "有点意思再观察(加深)", "有点意思再观察(没变)",
        "不合(打脸,我之前判断错了)", "不合(没变)",
    }
    verdict = data.get("verdict", "有点意思再观察(没变)")
    if verdict not in valid_verdicts:
        verdict = "有点意思再观察(没变)"
    recommended = data.get("recommended_action", "再派一次")
    if recommended not in ("开真人聊天", "再派一次", "跟我聊聊调方向"):
        recommended = "再派一次"

    summary = Summary(
        agent_chat_id=None,
        chat_session_id=session.id,
        host_user_id=host_user_id,
        summary_type="human_chat_observation",
        verdict=verdict,
        highlights=data.get("highlights", []),
        risks=data.get("risks", []),
        recommended_action=recommended,
        evidence_chunks=data.get("evidence_chunks", []),
    )
    # compare_to_agent_chat 落入 highlights 第一项作为前缀(MVP 简化,Phase 5 加独立字段)
    cmp_text = data.get("compare_to_agent_chat")
    if cmp_text:
        summary.highlights = [
            {"text": f"[对照前判断] {cmp_text}", "evidence_utterance_id": None}
        ] + (summary.highlights or [])

    db.add(summary)
    await db.commit()
    await db.refresh(summary)
    return summary
