"""Add single-use legacy Google account email claims."""
from alembic import op
import sqlalchemy as sa

revision = "20261009_email_claim"
down_revision = "20260513_add_password_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_account_claims",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("send_count", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("email_account_claims")
