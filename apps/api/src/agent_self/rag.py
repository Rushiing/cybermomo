"""
08 · 跟自己 Agent 对话 · RAG 检索

retrieve_context(user_id, query, ...) → 拼装"该宿主的相关上下文"给 LLM。

来源(全部按 host scope 严格过滤):
- md_segments :宿主自己 .md 的相关切片(向量距离)
- summaries   :宿主的简报(verdict + highlights + risks)
- agent_conversation_messages:同宿主历史对话片段(同一会话不重复检索)

不索引 / 不暴露:
- 对方 Agent 的 private_signals(铁律)
- agent_chat_messages(对方说过的 utterance)— 已经通过 summary 摘要呈现给宿主
- 平台底线拉黑相关元数据
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent_self.models import AgentConversation, AgentConversationMessage
from src.llm.gateway import llm_embed
from src.md.models import MdSegment
from src.summary.models import Summary


# pgvector 的 cosine 距离运算符:`<=>` 返回 0~2(0 = 完全相同)
# 在 SQLAlchemy 里走 .cosine_distance(query_vector) 表达式


ContextSource = Literal["md", "summary", "past_conversation"]


@dataclass
class ContextChunk:
    source: ContextSource
    ref_id: int            # md_segments.id / summaries.id / agent_conversation_messages.id
    text: str
    distance: float        # 0~2(越小越相关)
    metadata: dict         # source 各自的额外字段(segment_type / verdict / scope etc.)


async def retrieve_context(
    db: AsyncSession,
    *,
    user_id: int,
    query: str,
    top_k_per_source: int = 3,
    exclude_conversation_id: Optional[int] = None,
) -> list[ContextChunk]:
    """
    用 query 文本检索宿主自己的 md / summary / 过往对话片段。

    Args:
        user_id: 宿主 user_id(host scope 强制过滤)
        query: 用户问题文本(会先 embed 一次)
        top_k_per_source: 每个来源最多取几条
        exclude_conversation_id: 排除当前对话 id 的消息(避免拿当前对话自己当上下文)

    Returns:
        ContextChunk 列表,按 distance 升序(最相关在前)。
        空 query / embed 失败 / 没有数据时返回 []。

    注意:
        - md_segments.embedding / summaries.embedding / agent_conversation_messages.embedding
          是 NULL 的行会被自动跳过(SQL 层面 IS NULL 不参与 cosine_distance)
        - 调用方负责拼 prompt 时按 source 给段落标头(避免对话历史被当成"事实")
    """
    if not (query or "").strip():
        return []

    try:
        embed_resp = await llm_embed(query)
    except Exception as e:
        print(f"[rag] query embed failed: {e}")
        return []

    qv = embed_resp.vector

    out: list[ContextChunk] = []

    # --- md_segments(宿主自己的人格切片)---
    md_q = (
        select(
            MdSegment.id,
            MdSegment.content,
            MdSegment.segment_type,
            MdSegment.embedding.cosine_distance(qv).label("distance"),
        )
        .where(MdSegment.user_id == user_id)
        .where(MdSegment.embedding.is_not(None))
        .order_by("distance")
        .limit(top_k_per_source)
    )
    for row in (await db.execute(md_q)).all():
        out.append(ContextChunk(
            source="md",
            ref_id=row.id,
            text=row.content,
            distance=float(row.distance),
            metadata={"segment_type": row.segment_type},
        ))

    # --- summaries(宿主自己的简报)---
    sm_q = (
        select(
            Summary.id,
            Summary.verdict,
            Summary.summary_type,
            Summary.highlights,
            Summary.risks,
            Summary.recommended_action,
            Summary.embedding.cosine_distance(qv).label("distance"),
        )
        .where(Summary.host_user_id == user_id)
        .where(Summary.embedding.is_not(None))
        .order_by("distance")
        .limit(top_k_per_source)
    )
    for row in (await db.execute(sm_q)).all():
        # 把 summary 转成可读文本,RAG 看上下文时一眼明白
        text = _format_summary_for_rag(
            verdict=row.verdict,
            highlights=row.highlights,
            risks=row.risks,
            recommended=row.recommended_action,
        )
        out.append(ContextChunk(
            source="summary",
            ref_id=row.id,
            text=text,
            distance=float(row.distance),
            metadata={
                "verdict": row.verdict,
                "summary_type": row.summary_type,
            },
        ))

    # --- 过往对话片段(同宿主,跨会话)---
    conv_q = (
        select(
            AgentConversationMessage.id,
            AgentConversationMessage.conversation_id,
            AgentConversationMessage.role,
            AgentConversationMessage.content,
            AgentConversationMessage.embedding.cosine_distance(qv).label("distance"),
        )
        .join(
            AgentConversation,
            AgentConversation.id == AgentConversationMessage.conversation_id,
        )
        .where(AgentConversation.host_user_id == user_id)
        .where(AgentConversationMessage.embedding.is_not(None))
        .where(AgentConversationMessage.role != "system")  # system 提示不进检索
        .order_by("distance")
        .limit(top_k_per_source)
    )
    if exclude_conversation_id is not None:
        conv_q = conv_q.where(
            AgentConversationMessage.conversation_id != exclude_conversation_id
        )
    for row in (await db.execute(conv_q)).all():
        out.append(ContextChunk(
            source="past_conversation",
            ref_id=row.id,
            text=row.content,
            distance=float(row.distance),
            metadata={"role": row.role, "conversation_id": row.conversation_id},
        ))

    # 全局按 distance 排序(最相关在前)
    out.sort(key=lambda c: c.distance)
    return out


# === 辅助 ===

def _format_summary_for_rag(
    *,
    verdict: str,
    highlights: list,
    risks: list,
    recommended: str,
) -> str:
    """把 summary 字段拼成 LLM 看得懂的可读文本"""
    parts: list[str] = [f"判断: {verdict}"]
    for h in (highlights or [])[:3]:
        if isinstance(h, dict) and h.get("text"):
            parts.append(f"看点: {h['text']}")
    for r in (risks or [])[:2]:
        if isinstance(r, dict) and r.get("text"):
            parts.append(f"留意: {r['text']}")
    if recommended:
        parts.append(f"建议: {recommended}")
    return " | ".join(parts)
