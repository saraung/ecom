"""Add orders.rto_stock_restored (exactly-once RTO restock guard).

Revision ID: f1a2b3c4d5e6
Revises: b5d7f2a9c4e1
Create Date: 2026-09-29

RTO scans arrive in stages (INITIATED then DELIVERED) and webhooks retry,
so "did the status just change" can neither catch the late DELIVERED nor
survive a retry without double-restoring. A dedicated flag can.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'b5d7f2a9c4e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column(
        'rto_stock_restored', sa.Boolean(), nullable=False,
        server_default='false',
    ))
    op.create_index(
        'ix_orders_rto_stock_restored', 'orders',
        ['rto_stock_restored'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_orders_rto_stock_restored', table_name='orders')
    op.drop_column('orders', 'rto_stock_restored')
