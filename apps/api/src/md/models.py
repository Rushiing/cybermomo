"""
02 · .md 创建(v3 规则引擎)· ORM 模型

- md_documents:用户人格档案(profile_json 主消费源,镜像列做查询优化)
- md_segments:portrait_body 切片 + 向量(辅助)

v3 架构:.md 不再是 LLM 生成的 markdown,而是 v3 问卷 + 规则引擎产出的 profile_json。
content_md / dimension_scores / supplement 字段 DEPRECATED,仅作盲测期数据迁移备份。
"""
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt, UpdatedAt


class MdDocument(Base):
    __tablename__ = "md_documents"

    id: Mapped[PkInt]
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # v3 主消费源
    profile_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    profile_version: Mapped[str] = mapped_column(Text, nullable=False)
    portrait_body: Mapped[str | None] = mapped_column(Text)
    domains_interested: Mapped[list | None] = mapped_column(JSONB)
    domains_avoided: Mapped[list | None] = mapped_column(JSONB)

    # 沿用
    raw_answers: Mapped[dict | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    source_generation_id: Mapped[int | None] = mapped_column(Integer)

    # DEPRECATED 字段(盲测期遗留)
    content_md: Mapped[str | None] = mapped_column(Text)
    dimension_scores: Mapped[dict | None] = mapped_column(JSONB)
    supplement: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    __table_args__ = (
        UniqueConstraint("user_id", "version", name="uq_md_documents_user_version"),
        Index(
            "idx_md_documents_user_active",
            "user_id",
            unique=True,
            postgresql_where=sql_text("is_active = true"),
        ),
        Index("idx_md_documents_profile_version", "profile_version"),
        Index(
            "idx_md_documents_domains_interested",
            "domains_interested",
            postgresql_using="gin",
        ),
        Index(
            "idx_md_documents_domains_avoided",
            "domains_avoided",
            postgresql_using="gin",
        ),
    )


class MdSegment(Base):
    __tablename__ = "md_segments"

    id: Mapped[PkInt]
    md_document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("md_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_type: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        Index("idx_md_segments_doc", "md_document_id"),
        Index("idx_md_segments_user", "user_id"),
        Index(
            "idx_md_segments_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
