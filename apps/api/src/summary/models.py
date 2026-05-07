"""
06 · Agent 简报 · ORM 模型

- summaries:复用给:
    a) Agent 互聊后简报(agent_chat_id 非空,summary_type='agent_chat')
    b) 真人聊天前简报(§4.9)(后续添加 summary_type)
    c) 真人聊天后观察报告(chat_session_id 非空,summary_type='human_chat_observation')
- summary_decisions:用户在简报卡上的决策(开聊/再派/丢/调方向)

约束:agent_chat_id 与 chat_session_id 必须有且只有一个非空(由 CHECK 约束)。
"""
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[PkInt]

    # 关联前置场景:agent_chat_id 或 chat_session_id 必有且仅有一个非空
    agent_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("agent_chats.id", ondelete="CASCADE")
    )
    chat_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )

    host_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    summary_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="agent_chat", server_default="agent_chat"
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[list] = mapped_column(JSONB, nullable=False)
    risks: Mapped[list] = mapped_column(JSONB, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chunks: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        # 必有且仅有一个前置场景关联
        CheckConstraint(
            "(agent_chat_id IS NOT NULL AND chat_session_id IS NULL) OR "
            "(agent_chat_id IS NULL AND chat_session_id IS NOT NULL)",
            name="one_source",
        ),
        UniqueConstraint(
            "agent_chat_id", "host_user_id", "summary_type",
            name="uq_summaries_agent_chat_host_type",
        ),
        Index(
            "idx_summaries_host",
            "host_user_id",
            "created_at",
        ),
    )


class SummaryDecision(Base):
    __tablename__ = "summary_decisions"

    id: Mapped[PkInt]
    summary_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[CreatedAt]

    __table_args__ = (
        UniqueConstraint(
            "summary_id", "user_id", name="uq_summary_decisions_summary_user"
        ),
    )
