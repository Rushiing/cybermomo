"""drop UNIQUE on agent_chats.match_id (allow re_dispatch)

Revision ID: 20260508_drop_agent_chat_unique
Revises: 20260507_init_v1
Create Date: 2026-05-08 18:30:00

让一对 match 可以有多个 agent_chats:
- 第一场:status='done_*' 后,旧的标 're_dispatched'
- 第二场(再派一次):新建一行 status='running',后续生成新简报

旧的 UNIQUE (match_id) 必须去掉,否则第二次 INSERT 撞 pk_agent_chats_match_id_key。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260508_drop_agent_chat_unique"
down_revision: Union[str, None] = "20260507_init_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 名字两种都试一下(naming convention 不同)
    op.execute("ALTER TABLE agent_chats DROP CONSTRAINT IF EXISTS agent_chats_match_id_key")
    op.execute("ALTER TABLE agent_chats DROP CONSTRAINT IF EXISTS uq_agent_chats_match_id")


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_agent_chats_match_id", "agent_chats", ["match_id"]
    )
