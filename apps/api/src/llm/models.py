"""
LLM 跨模块基础设施 · ORM 模型

- prompt_versions:平台 prompt 全文 + 版本管理(同 module/prompt_name 同时只能一个 active)
- llm_call_log:所有 LLM 调用埋点(成本核算 / PE 调优 / 故障排查基座)
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text as sql_text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.shared.base import Base, CreatedAt, PkInt


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[PkInt]
    module: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_name: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        UniqueConstraint(
            "module", "prompt_name", "version",
            name="uq_prompt_versions_module_name_version",
        ),
        # 同 (module, prompt_name) 同时只能有一个 active 版本
        Index(
            "idx_prompt_versions_active",
            "module", "prompt_name",
            unique=True,
            postgresql_where=sql_text("is_active = true"),
        ),
    )


class LlmCallLog(Base):
    __tablename__ = "llm_call_log"

    id: Mapped[PkInt]
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("prompt_versions.id")
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(10, 6))
    error: Mapped[str | None] = mapped_column(Text)
    related_table: Mapped[str | None] = mapped_column(Text)
    related_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[CreatedAt]

    __table_args__ = (
        Index("idx_llm_call_log_role_time", "role", "created_at"),
        Index("idx_llm_call_log_user_time", "user_id", "created_at"),
        Index("idx_llm_call_log_related", "related_table", "related_id"),
    )
