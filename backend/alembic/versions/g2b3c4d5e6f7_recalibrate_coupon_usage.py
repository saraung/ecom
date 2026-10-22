"""Recalibrate coupons.times_used from real orders.

Revision ID: g2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-29

Usage is now counted once at checkout (order placement). Previously manual
codes were counted at cart-apply time (burned by abandoned carts) AND the
checkout path double-counted in places — so stored counters are inflated.
Recompute from non-cancelled/non-refunded orders, the same definition the
per-user limit already uses. (Enum values are stored as member NAMES.)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'g2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE coupons SET times_used = ("
        "SELECT COUNT(*) FROM orders "
        "WHERE orders.coupon_code = coupons.code "
        "AND orders.status NOT IN ('CANCELLED', 'REFUNDED'))"
    ))


def downgrade() -> None:
    """Downgrade schema (counters cannot be un-recomputed — no-op)."""
