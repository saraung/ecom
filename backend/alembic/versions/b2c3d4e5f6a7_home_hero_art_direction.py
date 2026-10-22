"""Add responsive art direction options to homepage hero blocks.

Revision ID: b2c3d4e5f6a7
Revises: y0a1b2c3d4e5, a1b2c3d4e5f7
Create Date: 2026-10-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = ("y0a1b2c3d4e5", "a1b2c3d4e5f7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Preserve the old full-bleed rendering for existing banners.
    op.add_column(
        "content_blocks",
        sa.Column("layout_mode", sa.String(length=20), nullable=False, server_default="overlay"),
    )
    op.add_column("content_blocks", sa.Column("mobile_image_url", sa.String(length=500), nullable=True))
    op.add_column("content_blocks", sa.Column("mobile_image_public_id", sa.String(length=500), nullable=True))
    op.add_column("content_blocks", sa.Column("image_alt", sa.String(length=500), nullable=True))
    op.add_column(
        "content_blocks",
        sa.Column("image_position", sa.String(length=20), nullable=False, server_default="center"),
    )


def downgrade() -> None:
    op.drop_column("content_blocks", "image_position")
    op.drop_column("content_blocks", "image_alt")
    op.drop_column("content_blocks", "mobile_image_public_id")
    op.drop_column("content_blocks", "mobile_image_url")
    op.drop_column("content_blocks", "layout_mode")
