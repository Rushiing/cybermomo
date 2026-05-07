"""init schema v1 · 创建全部 15 张表 + pgvector 扩展

Revision ID: 20260507_init_v1
Revises:
Create Date: 2026-05-07 14:30:00

按 cybermomo/工程拆解/_数据模型.md v0(v3 重写) 落地全部 schema:
- 01 auth: users, user_profiles
- 02 md: md_documents (v3 profile_json), md_segments
- 03 match: matches, matchpoints, match_hooks
- 04 agent_chat: agent_chats, agent_chat_messages
- 05 room: user_soft_blocklist, user_hard_blocklist
- 06 summary: summaries, summary_decisions
- 07 human_chat: chat_sessions, chat_messages, chat_callouts, chat_reports
- llm: prompt_versions, llm_call_log

包含 pgvector extension 创建。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260507_init_v1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- pgvector 扩展 ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- users / user_profiles ---
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("google_sub", sa.Text(), nullable=False, unique=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("google_name", sa.Text()),
        sa.Column("google_avatar_url", sa.Text()),
        sa.Column(
            "is_adult_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("onboarded_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_users_google_sub", "users", ["google_sub"])
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "user_profiles",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("age_band", sa.Text()),
        sa.Column("gender", sa.Text()),
        sa.Column("mbti", sa.Text()),
        sa.Column("avatar_url", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # --- md_documents / md_segments ---
    op.create_table(
        "md_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("profile_json", postgresql.JSONB(), nullable=False),
        sa.Column("profile_version", sa.Text(), nullable=False),
        sa.Column("portrait_body", sa.Text()),
        sa.Column("domains_interested", postgresql.JSONB()),
        sa.Column("domains_avoided", postgresql.JSONB()),
        sa.Column("raw_answers", postgresql.JSONB()),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("source_generation_id", sa.Integer()),
        # DEPRECATED 字段(盲测期遗留)
        sa.Column("content_md", sa.Text()),
        sa.Column("dimension_scores", postgresql.JSONB()),
        sa.Column("supplement", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "version", name="uq_md_documents_user_version"),
    )
    # 同一 user 同时只能有一个 active
    op.execute(
        "CREATE UNIQUE INDEX idx_md_documents_user_active "
        "ON md_documents(user_id) WHERE is_active = true"
    )
    op.create_index(
        "idx_md_documents_profile_version", "md_documents", ["profile_version"]
    )
    op.create_index(
        "idx_md_documents_domains_interested",
        "md_documents",
        ["domains_interested"],
        postgresql_using="gin",
    )
    op.create_index(
        "idx_md_documents_domains_avoided",
        "md_documents",
        ["domains_avoided"],
        postgresql_using="gin",
    )

    op.create_table(
        "md_segments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "md_document_id",
            sa.BigInteger(),
            sa.ForeignKey("md_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_type", sa.Text(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_md_segments_doc", "md_segments", ["md_document_id"])
    op.create_index("idx_md_segments_user", "md_segments", ["user_id"])
    op.execute(
        "CREATE INDEX idx_md_segments_embedding ON md_segments "
        "USING hnsw (embedding vector_cosine_ops)"
    )

    # --- matches / matchpoints / match_hooks ---
    op.create_table(
        "matches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_a_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_b_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("overall_score", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "is_wildcard",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("user_a_id < user_b_id", name="ck_matches_user_pair_order"),
    )
    op.create_index(
        "idx_matches_pair", "matches", ["user_a_id", "user_b_id"], unique=True
    )
    op.create_index("idx_matches_user_a", "matches", ["user_a_id"])
    op.create_index("idx_matches_user_b", "matches", ["user_b_id"])
    op.create_index("idx_matches_status", "matches", ["status"])

    op.create_table(
        "matchpoints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("a_source_segments", postgresql.JSONB(), nullable=False),
        sa.Column("b_source_segments", postgresql.JSONB(), nullable=False),
        sa.Column("similarity", sa.Numeric(5, 4), nullable=False),
        sa.Column("weight", sa.Numeric(5, 4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_matchpoints_match", "matchpoints", ["match_id"])

    op.create_table(
        "match_hooks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "matchpoint_id",
            sa.BigInteger(),
            sa.ForeignKey("matchpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("topic_id", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("hook_text", sa.Text(), nullable=False),
        sa.Column("sensitivity_level", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "sensitivity_level BETWEEN 0 AND 2",
            name="ck_match_hooks_sensitivity_range",
        ),
    )
    op.create_index(
        "idx_match_hooks_match_target",
        "match_hooks",
        ["match_id", "target_user_id"],
    )

    # --- agent_chats / agent_chat_messages ---
    op.create_table(
        "agent_chats",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("end_reason", sa.Text()),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_agent_chats_match", "agent_chats", ["match_id"])
    op.create_index("idx_agent_chats_status", "agent_chats", ["status"])

    op.create_table(
        "agent_chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_chat_id",
            sa.BigInteger(),
            sa.ForeignKey("agent_chats.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "speaker_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("topic_ref", sa.Text(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("utterance", sa.Text(), nullable=False),
        sa.Column("public_signals", postgresql.JSONB(), nullable=False),
        sa.Column("private_signals", postgresql.JSONB(), nullable=False),
        sa.Column("topic_close_payload", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_acm_chat_turn", "agent_chat_messages", ["agent_chat_id", "turn"]
    )

    # --- user_soft_blocklist / user_hard_blocklist ---
    op.create_table(
        "user_soft_blocklist",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "blocked_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_soft_block_user", "user_soft_blocklist", ["user_id"])

    op.create_table(
        "user_hard_blocklist",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "blocked_user_id",
            sa.BigInteger(),
            # 故意不带 ON DELETE CASCADE
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("violation_type", sa.Text(), nullable=False),
        sa.Column("violation_evidence_id", sa.BigInteger()),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_hard_block_user", "user_hard_blocklist", ["blocked_user_id"]
    )

    # --- chat_sessions(必须先于 summaries,因为 summaries.chat_session_id 引用它)---
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "match_id",
            sa.BigInteger(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_a_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_b_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "exit_action_by", sa.BigInteger(), sa.ForeignKey("users.id")
        ),
        sa.Column("exit_action", sa.Text()),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "user_a_id < user_b_id", name="ck_chat_sessions_user_pair_order"
        ),
    )
    op.create_index("idx_chat_sessions_match", "chat_sessions", ["match_id"])
    op.create_index(
        "idx_chat_sessions_user_a", "chat_sessions", ["user_a_id", "status"]
    )
    op.create_index(
        "idx_chat_sessions_user_b", "chat_sessions", ["user_b_id", "status"]
    )
    op.execute(
        "CREATE INDEX idx_chat_sessions_silent "
        "ON chat_sessions(last_message_at) WHERE status = 'active'"
    )

    # --- summaries / summary_decisions ---
    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "agent_chat_id",
            sa.BigInteger(),
            sa.ForeignKey("agent_chats.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "chat_session_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "host_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "summary_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'agent_chat'"),
        ),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("highlights", postgresql.JSONB(), nullable=False),
        sa.Column("risks", postgresql.JSONB(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("evidence_chunks", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(agent_chat_id IS NOT NULL AND chat_session_id IS NULL) OR "
            "(agent_chat_id IS NULL AND chat_session_id IS NOT NULL)",
            name="ck_summaries_one_source",
        ),
        sa.UniqueConstraint(
            "agent_chat_id",
            "host_user_id",
            "summary_type",
            name="uq_summaries_agent_chat_host_type",
        ),
    )
    op.create_index(
        "idx_summaries_host", "summaries", ["host_user_id", "created_at"]
    )

    op.create_table(
        "summary_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "summary_id",
            sa.BigInteger(),
            sa.ForeignKey("summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "summary_id", "user_id", name="uq_summary_decisions_summary_user"
        ),
    )

    # --- chat_messages / chat_callouts / chat_reports ---
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_chat_messages_session_time", "chat_messages", ["session_id", "sent_at"]
    )

    op.create_table(
        "chat_callouts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "host_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("callout_prompt", sa.Text(), nullable=False),
        sa.Column("callout_response", sa.Text(), nullable=False),
        sa.Column("context_message_ids", postgresql.JSONB()),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_chat_callouts_session_host",
        "chat_callouts",
        ["session_id", "host_user_id"],
    )

    op.create_table(
        "chat_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # 故意不带 ON DELETE CASCADE — 治理留底
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("chat_sessions.id"),
            nullable=False,
        ),
        sa.Column(
            "reporter_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "reported_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("content", sa.Text()),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("reviewer_note", sa.Text()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_chat_reports_status", "chat_reports", ["status", "created_at"]
    )

    # --- prompt_versions / llm_call_log ---
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("prompt_name", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "module", "prompt_name", "version",
            name="uq_prompt_versions_module_name_version",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_prompt_versions_active "
        "ON prompt_versions(module, prompt_name) WHERE is_active = true"
    )

    op.create_table(
        "llm_call_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "prompt_id",
            sa.BigInteger(),
            sa.ForeignKey("prompt_versions.id"),
        ),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cost_estimate", sa.Numeric(10, 6)),
        sa.Column("error", sa.Text()),
        sa.Column("related_table", sa.Text()),
        sa.Column("related_id", sa.BigInteger()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_llm_call_log_role_time", "llm_call_log", ["role", "created_at"]
    )
    op.create_index(
        "idx_llm_call_log_user_time", "llm_call_log", ["user_id", "created_at"]
    )
    op.create_index(
        "idx_llm_call_log_related",
        "llm_call_log",
        ["related_table", "related_id"],
    )


def downgrade() -> None:
    """完整回滚:倒序删表 + drop 扩展(谨慎使用)"""
    op.drop_table("llm_call_log")
    op.drop_table("prompt_versions")
    op.drop_table("chat_reports")
    op.drop_table("chat_callouts")
    op.drop_table("chat_messages")
    op.drop_table("summary_decisions")
    op.drop_table("summaries")
    op.drop_table("chat_sessions")
    op.drop_table("user_hard_blocklist")
    op.drop_table("user_soft_blocklist")
    op.drop_table("agent_chat_messages")
    op.drop_table("agent_chats")
    op.drop_table("match_hooks")
    op.drop_table("matchpoints")
    op.drop_table("matches")
    op.drop_table("md_segments")
    op.drop_table("md_documents")
    op.drop_table("user_profiles")
    op.drop_table("users")
    # pgvector 扩展不删,可能其他表用
