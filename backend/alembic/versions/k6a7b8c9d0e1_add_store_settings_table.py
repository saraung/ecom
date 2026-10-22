"""Add store_settings singleton table

Revision ID: k6a7b8c9d0e1
Revises: j5f6a7b8c9d0
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'j5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "store_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tax_rate", sa.Float(), nullable=False, server_default="0.18"),
        sa.Column("free_shipping_threshold", sa.Float(), nullable=False, server_default="1000.0"),
        sa.Column("shipping_cost", sa.Float(), nullable=False, server_default="50.0"),
        sa.Column("cod_fee", sa.Float(), nullable=False, server_default="50.0"),
        sa.Column("cod_min_order_value", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("cod_max_order_value", sa.Float(), nullable=False, server_default="10000.0"),
        sa.Column("restocking_fee_pending", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("restocking_fee_confirmed", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("restocking_fee_processing", sa.Float(), nullable=False, server_default="15.0"),
        sa.Column("refund_processing_days", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("pending_order_expiry_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("store_settings")
