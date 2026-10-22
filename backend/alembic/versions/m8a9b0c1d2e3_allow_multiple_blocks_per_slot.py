"""Allow multiple blocks per slot (slider support)

Revision ID: m8a9b0c1d2e3
Revises: l7a8b9c0d1e2
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'm8a9b0c1d2e3'
down_revision: Union[str, Sequence[str], None] = 'l7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop the one-block-per-slot unique constraint (Postgres auto-name).
    op.execute(
        "ALTER TABLE content_blocks "
        "DROP CONSTRAINT IF EXISTS content_blocks_key_key"
    )
    op.add_column(
        "content_blocks",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_content_blocks_key_sort", "content_blocks", ["key", "sort_order"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_content_blocks_key_sort", table_name="content_blocks")
    op.drop_column("content_blocks", "sort_order")
    op.create_unique_constraint("content_blocks_key_key", "content_blocks", ["key"])
