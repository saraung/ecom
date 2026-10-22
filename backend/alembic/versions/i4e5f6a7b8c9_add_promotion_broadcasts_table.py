"""Add promotion_broadcasts header table

Revision ID: i4e5f6a7b8c9
Revises: h3d4e5f6a7b8
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'h3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "promotion_broadcasts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column("link", sa.String(), nullable=True),
        sa.Column("recipients_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("emails_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("emails_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_promotion_broadcasts_created_at",
        "promotion_broadcasts",
        ["created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_promotion_broadcasts_created_at", table_name="promotion_broadcasts")
    op.drop_table("promotion_broadcasts")
