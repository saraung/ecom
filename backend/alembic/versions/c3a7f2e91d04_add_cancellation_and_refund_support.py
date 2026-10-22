"""Add order cancellation and refund support

- orders.cancellation_reason  — why the customer/admin cancelled
- orders.cancelled_at         — when the order was cancelled
- orders.refund_amount        — total amount refunded so far
- orders.refund_id            — Razorpay refund ID (rfnd_xxx)
- orders.refund_reason        — reason recorded with the refund
- orders.restocking_fee       — fee deducted from the refund
- orders.refunded_at          — when the refund was processed

Revision ID: c3a7f2e91d04
Revises: b1e5f7a93c2d
Create Date: 2026-08-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c3a7f2e91d04'
down_revision: Union[str, Sequence[str], None] = 'b1e5f7a93c2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'orders',
        sa.Column('cancellation_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('refund_amount', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
    )
    op.add_column(
        'orders',
        sa.Column('refund_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('refund_reason', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('restocking_fee', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
    )
    op.add_column(
        'orders',
        sa.Column('refunded_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orders', 'refunded_at')
    op.drop_column('orders', 'restocking_fee')
    op.drop_column('orders', 'refund_reason')
    op.drop_column('orders', 'refund_id')
    op.drop_column('orders', 'refund_amount')
    op.drop_column('orders', 'cancelled_at')
    op.drop_column('orders', 'cancellation_reason')
