"""Independent reverse provider identifiers and durable creation recovery."""
from alembic import op
import sqlalchemy as sa

revision = "w8e9f0a1b2c3"
down_revision = "v7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    for name, size in (("shiprocket_order_id", 100), ("shiprocket_shipment_id", 100), ("shipping_reference", 20)):
        op.add_column("return_requests", sa.Column(name, sa.String(size), nullable=True))
        op.create_index(f"ix_return_requests_{name}", "return_requests", [name], unique=True)
    op.add_column("return_requests", sa.Column("shipping_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("return_requests") as batch:
        batch.drop_column("shipping_requested_at")
        for name in ("shipping_reference", "shiprocket_shipment_id", "shiprocket_order_id"):
            batch.drop_index(f"ix_return_requests_{name}")
            batch.drop_column(name)
