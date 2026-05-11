"""
08 · 跟自己 Agent 对话 · ORM 模型

- agent_conversations:一个宿主 ↔ 自己 Agent 的会话(允许多个并存,按 scope 区分)
- agent_conversation_messages:消息流(user / assistant / system),assistant + user
  message 增量写 embedding 用于 RAG 检索"上次聊过类似的话题吗"

scope 取值:
- 'room'     宿主在 /room 简报上点「跟我 Agent 聊聊」开的会话
- 'plaza'    Phase 3 — 宿主在广场上对某个目标用户发起的探询会话
- 'revisit'  真人聊天结束后 Agent 主动种的回访会话
- 'general'  右下浮动 Agent 全局对话(无具体上下文)

context_refs JSONB 约定 — 软约束,前端读取按 scope 解析:
- room    : {"summary_id": int, "agent_chat_id": int}
- plaza   : {"target_user_id": int}
- revisit : {"chat_session_id": int, "peer_user_id": int}
- general : {} 或 null
"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[PkInt]
    host_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(
        Text, nullable=False, default="general", server_default="general"
    )
    title: Mapped[str | None] = mapped_column(Text)
    context_refs: Mapped[dict | None] = mapped_column(JSONB)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        CheckConstraint(
            "scope IN ('room', 'plaza', 'revisit', 'general')",
            name="scope_enum",
        ),
        Index("idx_agent_conv_host_recent", "host_user_id", "last_message_at"),
        Index("idx_agent_conv_host_scope", "host_user_id", "scope"),
    )


class AgentConversationMessage(Base):
    __tablename__ = "agent_conversation_messages"

    id: Mapped[PkInt]
    conversation_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("agent_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # assistant + user 消息异步写 embedding,system 消息一般留 NULL
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="role_enum",
        ),
        Index("idx_agent_conv_msg_conv_turn", "conversation_id", "turn"),
        # HNSW 用 cosine 距离(text-embedding-v3 已 L2 normalize)
        Index(
            "idx_agent_conv_msg_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
