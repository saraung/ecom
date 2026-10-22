"""Reconcile COD delivery-only paid flags without a collection record."""
from alembic import op

revision = "t5b6c7d8e9f0"
down_revision = "s4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE orders SET payment_status = 'cod_pending' "
               "WHERE payment_method = 'cod' AND payment_status = 'paid' AND NOT EXISTS "
               "(SELECT 1 FROM payments WHERE payments.order_id = orders.id "
               "AND lower(CAST(payments.provider AS TEXT)) = 'cod' "
               "AND lower(CAST(payments.status AS TEXT)) = 'succeeded')")


def downgrade():
    # Do not fabricate collections on downgrade. This is a truth correction.
    pass
