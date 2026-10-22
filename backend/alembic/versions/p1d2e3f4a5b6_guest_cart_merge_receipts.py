"""Idempotent per-entry guest cart merge receipts.

Revision ID: p1d2e3f4a5b6
Revises: o0c1d2e3f4a5
"""
from alembic import op
import sqlalchemy as sa

revision = "p1d2e3f4a5b6"
down_revision = "o0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("cart_merge_receipts",
        sa.Column("cart_id", sa.Uuid(), sa.ForeignKey("carts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("merge_key", sa.Uuid(), primary_key=True),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("cart_merge_receipts")
