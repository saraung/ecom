"""Add COD (Cash on Delivery) support

- orders.payment_method  (card | upi | cod) — the choice made at checkout
- orders.cod_fee         — flat COD fee included in grand_total
- paymentprovider enum   — new 'cod' value so COD collections can be recorded

Revision ID: b1e5f7a93c2d
Revises: 87332cd4a50a
Create Date: 2026-08-28 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b1e5f7a93c2d'
down_revision: Union[str, Sequence[str], None] = '87332cd4a50a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. New columns on orders
    op.add_column(
        'orders',
        sa.Column('payment_method', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('cod_fee', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0'),
    )

    # 2. Add 'cod' to the Postgres enum type (must run outside a transaction block)
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE paymentprovider ADD VALUE IF NOT EXISTS 'cod'")


def downgrade() -> None:
    """Downgrade schema."""
    # NOTE: PostgreSQL cannot remove enum values, so the 'cod' member of the
    # paymentprovider type is intentionally left in place on downgrade.
    op.drop_column('orders', 'cod_fee')
    op.drop_column('orders', 'payment_method')