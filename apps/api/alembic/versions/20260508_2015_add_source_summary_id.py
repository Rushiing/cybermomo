"""add chat_sessions.source_summary_id

Revision ID: 20260508_add_source_summary_id
Revises: 20260508_drop_agent_chat_unique
Create Date: 2026-05-08 20:15:00

让 chat_session 直接记下"是从哪张简报衍生过来的",
前端可以做双向链接(简报卡 → 进入聊天 / 聊天卡 → 回看那张简报)。

旧 session 没有这个字段(NULL 即可,前端容错处理)。
ON DELETE SET NULL:简报被删时(治理场景)session 还能存在。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260508_add_source_summary_id"
down_revision: Union[str, None] = "20260508_drop_agent_chat_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "source_summary_id",
            sa.BigInteger(),
            sa.ForeignKey("summaries.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_chat_sessions_source_summary",
        "chat_sessions",
        ["source_summary_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_chat_sessions_source_summary", table_name="chat_sessions")
    op.drop_column("chat_sessions", "source_summary_id")
