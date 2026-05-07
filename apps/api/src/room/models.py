"""
05 · 个人房间 · ORM 模型

个人房间本身是视图层(由 matches/summaries/chat_sessions 动态聚合卡片),不另存表。
仅这两张拉黑表:

- user_soft_blocklist:用户级软拉黑(可解除,不再被推荐)
- user_hard_blocklist:平台底线拉黑(违规留底,用户即使注销也保留)
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt


class UserSoftBlocklist(Base):
    __tablename__ = "user_soft_blocklist"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    blocked_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_soft_block_user", "user_id"),)


class UserHardBlocklist(Base):
    __tablename__ = "user_hard_blocklist"

    id: Mapped[PkInt]
    blocked_user_id: Mapped[int] = mapped_column(
        BigInteger,
        # 故意不带 ON DELETE CASCADE — 用户注销时硬拉黑记录保留
        ForeignKey("users.id"),
        nullable=False,
    )
    violation_type: Mapped[str] = mapped_column(Text, nullable=False)
    violation_evidence_id: Mapped[int | None] = mapped_column(BigInteger)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_hard_block_user", "blocked_user_id"),)
