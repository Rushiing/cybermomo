"""
01 · 用户注册 · ORM 模型

- users:账号身份(google_sub / email / 合规字段),稳定不变
- user_profiles:展示侧资料(昵称、年龄段、性别、MBTI、自定头像),可改
"""
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.shared.base import Base, CreatedAt, PkInt, UpdatedAt


class User(Base):
    __tablename__ = "users"

    id: Mapped[PkInt]
    google_sub: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    google_name: Mapped[str | None] = mapped_column(Text)
    google_avatar_url: Mapped[str | None] = mapped_column(Text)
    is_adult_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # 关系
    profile: Mapped["UserProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_users_google_sub", "google_sub"),
        Index("idx_users_email", "email"),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    nickname: Mapped[str] = mapped_column(Text, nullable=False)
    age_band: Mapped[str | None] = mapped_column(Text)
    gender: Mapped[str | None] = mapped_column(Text)
    mbti: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    user: Mapped["User"] = relationship(back_populates="profile")
