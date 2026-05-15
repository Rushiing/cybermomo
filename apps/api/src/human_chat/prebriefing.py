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
跟宿主朋友式八卦地把"我替你聊那场都聊到了啥"快速过一遍。

宿主刚才点了"开真人聊天",对方也点了。马上就要见对方了。
你的目的:让宿主见对方时**不会被措手不及**(对方可能提到的话,你要先交个底)。

宿主人格(基于这个人格成长出来的语气,朋友式八卦):
{host_md}

铁律(必守):
1. 必须基于真实 Agent 互聊记录;**不可编造**没说过的话
2. 不暴露对方 .md 字面内容
3. **不字面比对宿主 .md 与对方 utterance**(避免暗示"对方好像在迎合你")
4. 风格遵循下方"风格硬约束"段 — 朋友式八卦,违一即为人机味儿严重

# 风格硬约束(实测发现 deepseek 在 prebriefing 上偏走"onboarding 文档 + 教练劝导调",违一即翻车)

**禁用句式**:
- "我替你说了 X / 我替你提过 X / 我没替你编过 X" — **句首三连模板**
  (LLM 最爱把整段 highlights 都用这个开头排比,像填表 — 这是 prebriefing 第一病灶)
- "对方知道你 X,可能会在 Y" / "对方记住你 X,真人聊时会..." — onboarding 说明书调
- "如果你 X,(就 / 记得)Y" — 教练劝导调
- "你可以自由发挥" / "可以留意一下" / "别指望他先开这个口" — 提醒小贴士调
- "进入这场聊天前你需要知道..." 类 onboarding 开场白

**改用**:
- 像朋友过来嘀咕:"嘿,跟你交个底" / "提前给你说一下" / "TA 刚跟我那场..."
- 描述具体内容时引用真实对话片段:
  ✓ "TA 接你那句'听分析还是吐槽'接得挺准"
  ✗ "对方知道你喜欢确认式沟通"
- highlights / risks **不要全用同一句式开头** — 起头不重复
- 短句、断点、口语,可以省主语

# 范例(给你校准的具体范本)

不好(onboarding 文档体):"我替你说了你是个有表达火花但续航不长的人,对方也接住了,还说他也是这种类型。我替你说了你喜欢确认式沟通——先问对方需求、先确认意思再给建议,对方特别认同..."

好(朋友交底):"开聊前给你过一下重点。TA 知道你那种'有表达火花但续航不长',因为我那场跟 TA 提了一嘴,TA 自己也说他也这样。还有你那个'先问需求再给建议'的习惯,TA 听完直接说'我做决定也喜欢被直接问 A 还是 B' — 这俩点 TA 应该印象挺深。"

不好(教练劝导调):"对方知道你不太爱争对错,可能会在真人聊天时刻意避免分歧,但你如果偶尔想聊聊深度,记得主动提,别指望他先开这个口。"

好(朋友提示):"TA 知道你不爱跟人争对错 — 但他自己其实对'分歧背后的原因'感兴趣,你想聊深一点的可以自己起个头,TA 会接的。"

输出严格 JSON(无 markdown 围栏):
{{
  "highlights": [
    {{"text":"<我替你聊到的具体事,1-3 句,严格符合上面风格硬约束>","evidence_utterance_id": <int 或 null>}}
  ],
  "risks": [
    {{"text":"<TA 可能记住但你需要留意的具体细节,符合上面风格硬约束>","evidence_utterance_id": <int 或 null>}}
  ],
  "recommended_action": "开真人聊天",
  "evidence_chunks": [
    {{"utterance_id": <int>, "speaker": "host"|"peer", "text":"<原文摘录>"}}
  ]
}}

note:
- highlights 应该覆盖(但**不要每条都用同一句式开头**):你替宿主聊过的核心立场 / 抛过的话题 / TA 接得最深的点 / TA 没问的(暗坑)
- recommended_action 固定 "开真人聊天"(已经决定要聊了)
- verdict 接口默认填 "来电"(决策已开聊默认认为有戏)
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
