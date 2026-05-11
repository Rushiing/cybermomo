"""add RAG infra · summaries.embedding + agent_conversations + agent_conversation_messages

Revision ID: 20260511_add_rag_infra
Revises: 20260508_add_source_summary_id
Create Date: 2026-05-11 14:30:00

为 Phase 1 (chat_with_my_agent Pro 版)铺路:
- summaries 加 embedding 列(Vector 1024 维,对齐 md_documents/md_segments.embedding)
  + HNSW cosine 索引,RAG 检索"过去聊过哪场跟这个相关"
- agent_conversations 表:宿主 ↔ 自己 Agent 的对话会话
  scope ∈ {room, plaza, revisit, general},context_refs JSONB 软约束
- agent_conversation_messages 表:消息流(user / assistant / system)
  embedding 列异步回填 + HNSW 索引,RAG 检索上次聊过的相关片段

铁律提醒(代码层面强制):
- 对方 Agent 的 private_signals 永远不进入 agent_conversation_messages.content
- .md 字面原文不进入 content,只能存 Agent 重述后的摘要

旧 summaries.embedding 一律 NULL,由 scripts/backfill_embeddings.py 一次性回填。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260511_add_rag_infra"
down_revision: Union[str, None] = "20260508_add_source_summary_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- summaries.embedding ---
    op.add_column(
        "summaries",
        sa.Column("embedding", Vector(1024), nullable=True),
    )
    # HNSW 索引(cosine);CREATE INDEX 直接走 op.execute 以拿到 USING hnsw 语法
    op.execute(
        "CREATE INDEX idx_summaries_embedding ON summaries "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # --- agent_conversations ---
    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "host_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sa.Text(),
            nullable=False,
            server_default="general",
        ),
        sa.Column("title", sa.Text()),
        sa.Column("context_refs", sa.dialects.postgresql.JSONB()),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "scope IN ('room', 'plaza', 'revisit', 'general')",
            name="ck_agent_conversations_scope_enum",
        ),
    )
    op.create_index(
        "idx_agent_conv_host_recent",
        "agent_conversations",
        ["host_user_id", "last_message_at"],
    )
    op.create_index(
        "idx_agent_conv_host_scope",
        "agent_conversations",
        ["host_user_id", "scope"],
    )

    # --- agent_conversation_messages ---
    op.create_table(
        "agent_conversation_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.BigInteger(),
            sa.ForeignKey("agent_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="ck_agent_conversation_messages_role_enum",
        ),
    )
    op.create_index(
        "idx_agent_conv_msg_conv_turn",
        "agent_conversation_messages",
        ["conversation_id", "turn"],
    )
    op.execute(
        "CREATE INDEX idx_agent_conv_msg_embedding "
        "ON agent_conversation_messages USING hnsw "
        "(embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_conv_msg_embedding")
    op.drop_index(
        "idx_agent_conv_msg_conv_turn", table_name="agent_conversation_messages"
    )
    op.drop_table("agent_conversation_messages")

    op.drop_index("idx_agent_conv_host_scope", table_name="agent_conversations")
    op.drop_index("idx_agent_conv_host_recent", table_name="agent_conversations")
    op.drop_table("agent_conversations")

    op.execute("DROP INDEX IF EXISTS idx_summaries_embedding")
    op.drop_column("summaries", "embedding")
