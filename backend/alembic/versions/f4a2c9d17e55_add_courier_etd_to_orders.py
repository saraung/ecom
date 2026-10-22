"""add courier etd and expected delivery date to orders

Revision ID: f4a2c9d17e55
Revises: e2c9f4b17a3d
Create Date: 2026-09-26

Stores the courier ETD text ("3-4 Days") chosen at AWB assignment plus a
concrete expected_delivery_date, so the storefront can show Amazon-style
"Arriving by …" without recomputing from courier text on every read.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f4a2c9d17e55'
down_revision: Union[str, Sequence[str], None] = 'e2c9f4b17a3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('orders', sa.Column('courier_etd', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('orders', sa.Column('expected_delivery_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('orders', 'expected_delivery_date')
    op.drop_column('orders', 'courier_etd')
