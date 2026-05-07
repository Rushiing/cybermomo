"""
SQLAlchemy declarative Base + 公共字段 mixin

所有 ORM 模型继承 Base。
"""
from datetime import datetime
from typing import Annotated

from sqlalchemy import BigInteger, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# 命名约定:迁移生成的约束名一致
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ========================================
# 公共字段类型(类型别名,便于复用)
# ========================================

# BIGSERIAL PRIMARY KEY
PkInt = Annotated[
    int, mapped_column(BigInteger, primary_key=True, autoincrement=True)
]

# created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
CreatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
]

# updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()(onupdate 由触发器或 ORM 维护)
UpdatedAt = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    ),
]
