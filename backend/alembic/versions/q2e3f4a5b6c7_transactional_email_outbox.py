"""Transactional email outbox.

Revision ID: q2e3f4a5b6c7
Revises: p1d2e3f4a5b6
"""
from alembic import op
import sqlalchemy as sa

revision = "q2e3f4a5b6c7"
down_revision = "p1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("email_outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("to_email", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("plain_text", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_email_outbox_event_key", "email_outbox", ["event_key"], unique=True)
    op.create_index("ix_email_outbox_next_attempt_at", "email_outbox", ["next_attempt_at"])


def downgrade():
    op.drop_table("email_outbox")
