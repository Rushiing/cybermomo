"""
03 · 匹配引擎 · ORM 模型

- matches:一对用户 + overall_score + wildcard 标记
- matchpoints:匹配点(供脱敏 Agent 消费)
- match_hooks:脱敏 Agent 产出的话题钩子
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt, UpdatedAt


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[PkInt]
    user_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    is_wildcard: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    __table_args__ = (
        # 强制对称:小 id 在前,避免重复对
        CheckConstraint("user_a_id < user_b_id", name="user_pair_order"),
        Index("idx_matches_pair", "user_a_id", "user_b_id", unique=True),
        Index("idx_matches_user_a", "user_a_id"),
        Index("idx_matches_user_b", "user_b_id"),
        Index("idx_matches_status", "status"),
    )


class Matchpoint(Base):
    __tablename__ = "matchpoints"

    id: Mapped[PkInt]
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    a_source_segments: Mapped[list] = mapped_column(JSONB, nullable=False)
    b_source_segments: Mapped[list] = mapped_column(JSONB, nullable=False)
    similarity: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (Index("idx_matchpoints_match", "match_id"),)


class MatchHook(Base):
    __tablename__ = "match_hooks"

    id: Mapped[PkInt]
    match_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    matchpoint_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("matchpoints.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    sensitivity_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        CheckConstraint(
            "sensitivity_level BETWEEN 0 AND 2", name="sensitivity_range"
        ),
        Index("idx_match_hooks_match_target", "match_id", "target_user_id"),
    )
