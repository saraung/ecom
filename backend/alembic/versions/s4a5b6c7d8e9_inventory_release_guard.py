"""Once-only inventory release guard.

Revision ID: s4a5b6c7d8e9
Revises: r3f4a5b6c7d8
"""
from alembic import op
import sqlalchemy as sa

revision = "s4a5b6c7d8e9"
down_revision = "r3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("orders", sa.Column("stock_released", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Existing terminal cancellations/refunds were handled by the old release
    # paths. Conservatively do not add stock again for historical rows.
    op.execute("UPDATE orders SET stock_released = true WHERE rto_stock_restored = true "
               "OR cancelled_at IS NOT NULL OR lower(CAST(status AS TEXT)) IN ('cancelled', 'refunded')")


def downgrade():
    op.drop_column("orders", "stock_released")
