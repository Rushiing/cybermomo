"""drop 'chat_with_my_agent' rows from summary_decisions

Revision ID: 20260513_drop_chat_with_my_agent_decisions
Revises: 20260512_resync_users_id_seq
Create Date: 2026-05-13 12:00:00

「跟我 Agent 聊聊」从 decision 解耦 → 改成持续性沉思行为,走单独的
POST /api/summary/{id}/agent-chat。历史 summary_decisions 里的
chat_with_my_agent 行没业务意义(只是个 lock,挡住用户后续真决策),
一律删掉,让卡片重新开放给真决策。

AgentConversation(scope=room)那一头不动 — 对话记录是有价值的,保留。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260513_drop_chat_with_my_agent_decisions"
down_revision: Union[str, None] = "20260512_resync_users_id_seq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM summary_decisions WHERE decision = 'chat_with_my_agent'"
    )


def downgrade() -> None:
    # 数据删除不可逆 — no-op
    pass
