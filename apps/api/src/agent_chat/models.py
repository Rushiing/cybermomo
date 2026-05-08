"""
04 · Agent 互聊 · ORM 模型

- agent_chats:一场 Agent 互聊会话
- agent_chat_messages:互聊消息流(public_signals 公开 / private_signals 仅本方可见)

铁律:`private_signals` 在 API 层面只能由"己方 Agent + 后台分析"访问,对方 Agent
prompt 上下文里不出现(在 src/llm/ 拼 context 时过滤)。
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class AgentChat(Base):
    __tablename__ = "agent_chats"

    id: Mapped[PkInt]
    match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("matches.id", ondelete="CASCADE"),
        nullable=False,
        # 注:不再 unique。
        # 第一场结束(done_*)后,标记为 're_dispatched',再派一次会新建一行 status='running'
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="running", server_default="running"
    )
    end_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_agent_chats_match", "match_id"),
        Index("idx_agent_chats_status", "status"),
    )


class AgentChatMessage(Base):
    __tablename__ = "agent_chat_messages"

    id: Mapped[PkInt]
    agent_chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("agent_chats.id", ondelete="CASCADE"), nullable=False
    )
    speaker_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    turn: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_ref: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    public_signals: Mapped[dict] = mapped_column(JSONB, nullable=False)
    private_signals: Mapped[dict] = mapped_column(JSONB, nullable=False)
    topic_close_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_acm_chat_turn", "agent_chat_id", "turn"),)
