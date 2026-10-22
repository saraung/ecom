"""Shared owned chat sessions and request budgets."""
from alembic import op
import sqlalchemy as sa

revision = "u6c7d8e9f0a1"
down_revision = "t5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("chat_sessions", sa.Column("id", sa.Uuid(), primary_key=True),
                    sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id")),
                    sa.Column("history", sa.JSON(), nullable=False),
                    sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_chat_sessions_expires_at", "chat_sessions", ["expires_at"])
    op.create_table("chat_rate_limits", sa.Column("key", sa.String(64), primary_key=True),
                    sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("count", sa.Integer(), nullable=False))
    op.create_index("ix_chat_rate_limits_window_start", "chat_rate_limits", ["window_start"])


def downgrade():
    op.drop_table("chat_rate_limits")
    op.drop_table("chat_sessions")
