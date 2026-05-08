"""
07 · 真人聊天室 · ORM 模型

- chat_sessions:真人聊天会话(不删,作观察素材保留)
- chat_messages:真人聊天消息(文字 / 图片)
- chat_callouts:用户求助 Agent 的私有记录(host 私有,对方完全不可见)
- chat_reports:举报记录(治理留底,即使被举报方注销也保留)

铁律:chat_callouts 任何 SELECT 必须 WHERE host_user_id = current_user.id
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[PkInt]
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    # 从哪张简报衍生而来(再派之后,同 match 多张简报里只有触发者那张)
    # ON DELETE SET NULL:简报被治理删时,session 不应被殃及
    source_summary_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("summaries.id", ondelete="SET NULL")
    )
    user_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    exit_action_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
    )
    exit_action: Mapped[str | None] = mapped_column(Text)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        CheckConstraint("user_a_id < user_b_id", name="user_pair_order"),
        Index("idx_chat_sessions_match", "match_id"),
        Index("idx_chat_sessions_user_a", "user_a_id", "status"),
        Index("idx_chat_sessions_user_b", "user_b_id", "status"),
        Index("idx_chat_sessions_source_summary", "source_summary_id"),
        Index(
            "idx_chat_sessions_silent",
            "last_message_at",
            postgresql_where=(("status = 'active'")),
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[PkInt]
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_chat_messages_session_time", "session_id", "sent_at"),)


class ChatCallout(Base):
    __tablename__ = "chat_callouts"

    id: Mapped[PkInt]
    session_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    host_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    callout_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    callout_response: Mapped[str] = mapped_column(Text, nullable=False)
    context_message_ids: Mapped[list | None] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        Index("idx_chat_callouts_session_host", "session_id", "host_user_id"),
    )


class ChatReport(Base):
    __tablename__ = "chat_reports"

    id: Mapped[PkInt]
    # 故意不带 ON DELETE CASCADE — 治理留底
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id"), nullable=False
    )
    reporter_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    reported_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_chat_reports_status", "status", "created_at"),)
