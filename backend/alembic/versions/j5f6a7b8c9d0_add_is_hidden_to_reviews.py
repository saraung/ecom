"""Add is_hidden moderation flag to reviews

Revision ID: j5f6a7b8c9d0
Revises: i4e5f6a7b8c9
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'i4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "reviews",
        sa.Column(
            "is_hidden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_reviews_is_hidden", "reviews", ["is_hidden"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_reviews_is_hidden", table_name="reviews")
    op.drop_column("reviews", "is_hidden")
