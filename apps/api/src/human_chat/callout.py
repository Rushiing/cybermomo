"""
07 · 真人聊天 · 旁观者 / 僚机 Agent (callout)

场景:用户在真人聊天里点输入框侧 callout 图标 → Agent 给建议。
- Agent 看得到对方的 utterance(因为旁观)
- Agent **对对方完全隐形**(callout 通道私有)
- Agent **不字面比对宿主 .md 与对方 utterance**

完整 prompt v0:cybermomo/落地拆解/07-真人聊天室/01-旁观者Agentprompt-v0.md
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.human_chat.schemas import CalloutResponse
from src.llm.gateway import llm_chat
from src.llm.types import Message
from src.match.desensitize import _parse_loose_json
from src.md.models import MdDocument
from src.human_chat.models import ChatCallout, ChatMessage, ChatSession


CALLOUT_SYSTEM_TEMPLATE = """\
你是宿主的 Agent — 现在在真人聊天里**旁观 + 僚机**模式。

宿主刚才点了 callout 图标找你帮忙(对方真人完全看不到这个对话)。
你的角色:基于对方的真人话 + 宿主人格,给宿主**具体可操作**的建议(措辞 / 节奏 / 解读对方语气)。

宿主人格:
{host_md}

铁律(必守):
1. 你**对对方真人完全隐形**,callout 内容绝不能让对方看到
2. **不字面比对宿主 .md 与对方话**(不要说"她说的 X 跟你 .md 里 Y 对得上"这类)
3. 不替宿主编造没说过的事;不怂恿宿主做反人格的事
4. 风格:朋友式八卦 + 具体可执行,不是空洞的人生建议

输出严格 JSON(无 markdown 围栏):
{{
  "response_text": "<给宿主的回应,可以包含:解读对方 / 建议措辞 / 提醒留意,2-6 句>",
  "hint_message_id": <int 或 null,如果你的建议是针对对方某条具体消息的话>,
  "emotional_read": null | {{
    "tone": "<对方语气一词:松弛 / 客气 / 戒备 / 开放 / 焦虑 / ...>",
    "confidence": "low" | "medium" | "high",
    "note": "<不诛心的简短说明>"
  }}
}}
"""


USER_PAYLOAD_TEMPLATE = """\
当前真人聊天上下文(双方真实话):
{messages}

历史 callout(只你和宿主之间的):
{callouts}

宿主刚才问你:
{prompt}

引用对方的具体消息 ids(如有):{context_ids}
"""


async def run_callout(
    db: AsyncSession,
    *,
    session: ChatSession,
    host_user_id: int,
    callout_prompt: str,
    context_message_ids: Optional[list[int]] = None,
) -> ChatCallout:
    """
    跑一次 callout。LLM 调用 + 写 chat_callouts 表(host 私有)。
    """
    if host_user_id not in (session.user_a_id, session.user_b_id):
        raise ValueError("非该 session 参与者,不能 callout")

    # 拉宿主 profile
    profile = (await db.execute(
        select(MdDocument).where(
            MdDocument.user_id == host_user_id,
            MdDocument.is_active.is_(True),
        )
    )).scalar_one_or_none()

    # 拉真人聊天 messages(双方都看得到)
    messages = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.sent_at)
    )).scalars().all()
    messages_data = [
        {
            "id": m.id,
            "sender": "host" if m.sender_user_id == host_user_id else "peer",
            "type": m.content_type,
            "content": m.content if m.content_type == "text" else "[图片]",
            "sent_at": m.sent_at.isoformat(),
        }
        for m in messages
    ]

    # 历史 callout(只本人的)
    callouts = (await db.execute(
        select(ChatCallout)
        .where(
            ChatCallout.session_id == session.id,
            ChatCallout.host_user_id == host_user_id,
        )
        .order_by(ChatCallout.created_at)
    )).scalars().all()
    callouts_data = [
        {"prompt": c.callout_prompt, "response": c.callout_response}
        for c in callouts
    ]

    system = CALLOUT_SYSTEM_TEMPLATE.format(
        host_md=json.dumps(profile.profile_json if profile else {}, ensure_ascii=False),
    )
    user_payload = USER_PAYLOAD_TEMPLATE.format(
        messages=json.dumps(messages_data, ensure_ascii=False, indent=2),
        callouts=json.dumps(callouts_data, ensure_ascii=False, indent=2),
        prompt=callout_prompt,
        context_ids=context_message_ids or [],
    )

    resp = await llm_chat(
        role="callout",
        messages=[Message(role="user", content=user_payload)],
        system=system,
        max_tokens=1024,
        temperature=0.7,
        db=db,
        user_id=host_user_id,
        related_table="chat_sessions",
        related_id=session.id,
    )

    data = _parse_loose_json(resp.text) or {}
    response_text = str(data.get("response_text", ""))[:4000]
    if not response_text:
        # fallback:LLM 失败时给一条占位
        response_text = "我先想想……稍等(LLM 解析失败,你可以再问一次)。"

    callout = ChatCallout(
        session_id=session.id,
        host_user_id=host_user_id,
        callout_prompt=callout_prompt,
        callout_response=response_text,
        context_message_ids=context_message_ids or [],
        model=resp.model,
    )
    db.add(callout)
    await db.commit()
    await db.refresh(callout)
    return callout
