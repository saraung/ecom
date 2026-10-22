"""Durable payment creation attempts.

Revision ID: r3f4a5b6c7d8
Revises: q2e3f4a5b6c7
"""
from alembic import op
import sqlalchemy as sa

revision = "r3f4a5b6c7d8"
down_revision = "q2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("payment_creations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("response", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_payment_creations_order_id"))


def downgrade():
    op.drop_table("payment_creations")
