"""add password-auth columns + is_system_mock; relax google_sub / email NOT NULL

Revision ID: 20260513_add_password_auth
Revises: 20260513_drop_cwma_decisions
Create Date: 2026-05-13 15:00:00

双轨认证 schema:
- google_sub: NOT NULL → NULLABLE(密码用户没 sub);保留 UNIQUE,但通过
  partial unique index 实现 "WHERE google_sub IS NOT NULL"
- email: NOT NULL → NULLABLE(密码注册选填,且不验证)
- 新 username VARCHAR(20) NULLABLE + partial unique index + CHECK 正则
- 新 password_hash VARCHAR(255) NULLABLE(只密码用户填)
- 新 is_system_mock BOOLEAN DEFAULT false(cold_start seed 标记)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260513_add_password_auth"
down_revision: Union[str, None] = "20260513_drop_cwma_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- google_sub / email 放宽 NOT NULL ----
    op.alter_column("users", "google_sub", existing_type=sa.Text(), nullable=True)
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=True)

    # google_sub 原 UNIQUE 是列约束,现在用 partial unique index 替代,
    # 这样 NULL 值不互相冲突;旧的 UNIQUE 约束自动随列定义保留 — Postgres 允许多 NULL
    # 所以这里不需要改 UNIQUE,只是确认 — 但为了清晰,显式 drop 旧约束再加 partial
    # 注:Postgres 默认 UNIQUE 允许 NULL 不冲突(标准行为),所以旧 UNIQUE 仍 OK
    # 不动它

    # ---- 新列 ----
    op.add_column(
        "users",
        sa.Column("username", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_system_mock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # username partial unique index(允许 NULL,非 NULL 唯一)
    op.execute(
        "CREATE UNIQUE INDEX uq_users_username_notnull "
        "ON users(username) WHERE username IS NOT NULL"
    )
    # username 格式 CHECK(3-20 字符,字母数字下划线)
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_username_format "
        "CHECK (username IS NULL OR username ~ '^[a-zA-Z0-9_]{3,20}$')"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_auth_method "
        "CHECK (google_sub IS NOT NULL OR (username IS NOT NULL AND password_hash IS NOT NULL))"
    )
    op.create_index("idx_users_username", "users", ["username"])


def downgrade() -> None:
    op.drop_index("idx_users_username", table_name="users")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_auth_method")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_username_format")
    op.execute("DROP INDEX IF EXISTS uq_users_username_notnull")
    op.drop_column("users", "is_system_mock")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")
    # 回 NOT NULL 前需要回填,downgrade 不保证业务数据,这里只恢复列约束
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "google_sub", existing_type=sa.Text(), nullable=False)
