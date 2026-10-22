"""Delivered product returns with private evidence and existing refund linkage."""
from alembic import op
import sqlalchemy as sa

revision = "v7d8e9f0a1b2"
down_revision = "u6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    timestamps = ["created_at", "updated_at", "approved_at", "rejected_at", "shipped_at",
                  "received_at", "inspected_at", "refund_requested_at", "refunded_at", "cancelled_at"]
    op.create_table("return_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(14), nullable=False),
        sa.Column("reason", sa.String(17), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("decision_note", sa.String(1000)), sa.Column("inspection_note", sa.String(1000)),
        sa.Column("inspection_passed", sa.Boolean()),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("return_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("refund_attempts", sa.Integer(), nullable=False),
        sa.Column("tracking_number", sa.String(100)), sa.Column("tracking_provider", sa.String(20)),
        sa.Column("courier_name", sa.String(100)), sa.Column("tracking_status", sa.String(100)),
        *(sa.Column(name, sa.DateTime(timezone=True), nullable=name not in ("created_at", "updated_at")) for name in timestamps),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_return_owner_key"),
        sa.CheckConstraint("refund_amount > 0 AND return_fee >= 0", name="ck_return_amounts"),
        sa.CheckConstraint("refund_attempts >= 0", name="ck_return_attempts"),
        sa.CheckConstraint("status IN ('requested','approved','rejected','return_shipped','received','inspection','refund_pending','refunded','cancelled')", name="return_status"),
        sa.CheckConstraint("reason IN ('damaged','wrong_product','defective','missing_accessory','wrong_variant','changed_mind','other')", name="return_reason"))
    for name in ("order_id", "user_id", "status", "reason", "created_at"):
        op.create_index(f"ix_return_requests_{name}", "return_requests", [name])
    op.create_index("ix_return_requests_tracking_number", "return_requests", ["tracking_number"], unique=True)
    op.create_table("return_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("return_id", sa.Uuid(), sa.ForeignKey("return_requests.id"), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), sa.ForeignKey("order_items.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("return_id", "order_item_id", name="uq_return_item"),
        sa.CheckConstraint("quantity > 0 AND amount >= 0", name="ck_return_item_values"))
    for name in ("return_id", "order_item_id"):
        op.create_index(f"ix_return_items_{name}", "return_items", [name])
    op.create_table("return_evidence",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("return_id", sa.Uuid(), sa.ForeignKey("return_requests.id"), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False, unique=True),
        sa.Column("filename", sa.String(160), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_return_evidence_size"))
    op.create_index("ix_return_evidence_return_id", "return_evidence", ["return_id"])
    op.create_table("return_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("return_id", sa.Uuid(), sa.ForeignKey("return_requests.id"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(60), nullable=False), sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False), sa.Column("note", sa.String(1000)),
        sa.Column("details", sa.JSON(), nullable=False), sa.Column("event_key", sa.String(180), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for name in ("return_id", "created_at"):
        op.create_index(f"ix_return_events_{name}", "return_events", [name])
    op.add_column("refunds", sa.Column("return_request_id", sa.Uuid(), nullable=True))
    op.add_column("refunds", sa.Column("manual_transfer_reference", sa.String(200), nullable=True))
    with op.batch_alter_table("refunds") as batch:
        batch.create_foreign_key("fk_refunds_return_request", "return_requests", ["return_request_id"], ["id"])
    op.create_index("ix_refunds_return_request_id", "refunds", ["return_request_id"])


def downgrade():
    op.drop_index("ix_refunds_return_request_id", table_name="refunds")
    with op.batch_alter_table("refunds") as batch:
        batch.drop_constraint("fk_refunds_return_request", type_="foreignkey")
        batch.drop_column("manual_transfer_reference")
        batch.drop_column("return_request_id")
    for table in ("return_events", "return_evidence", "return_items", "return_requests"):
        op.drop_table(table)
