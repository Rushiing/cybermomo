"""resync users.id sequence with current max(id)

Revision ID: 20260512_resync_users_id_seq
Revises: 20260511_add_rag_infra
Create Date: 2026-05-12 16:30:00

修 mock auth fallback 显式插 id 留下的 sequence 不同步 bug:
- 之前 dev fallback 用 X-Mock-User-Id=2 触发 → INSERT users(id=2,...)
- Postgres 显式指定 id 时不自增 sequence,users_id_seq 还在 1
- 之后 OAuth 真用户 INSERT(不带 id,走 sequence)→ nextval=2 → 撞 pk_users

幂等:setval 到 MAX(id),不影响业务数据。新部署的 DB 这个 migration 也安全
跑(空表时 MAX=NULL,GREATEST 兜底为 1)。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20260512_resync_users_id_seq"
down_revision: Union[str, None] = "20260511_add_rag_infra"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # setval 第二个参数是"下次 nextval 返回的值减一",所以传 MAX(id)
    # 第三个参数 false 让下一次 nextval 直接返回 MAX(id)+1,不重复 MAX(id) 本身
    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('users', 'id'),
            GREATEST(COALESCE((SELECT MAX(id) FROM users), 0), 1),
            true
        )
    """)


def downgrade() -> None:
    # 无意义 — 序列回退会再次引发同样的冲突。no-op。
    pass
