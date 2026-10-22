"""COD remittance reconciliation tables and permissions.

Revision ID: z1b2c3d4e5f6
Revises: e3f4a5b6c7d8
Create Date: 2026-10-20

Additive only:
- ``cod_remittances`` / ``cod_remittance_items`` track courier payouts.
- ``orders.cod_remitted_amount`` and friends denormalize allocation state.
- ``cod.view`` / ``cod.reconcile`` permissions are seeded idempotently.

No Payment rows are created or changed by this migration. The existing
customer-collection ``Payment(provider=cod)`` remains the only revenue event.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES


revision: str = "z1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_KEYS = ("cod.view", "cod.reconcile")


def upgrade() -> None:
    op.create_table(
        "cod_remittances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("crf_id", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("remittance_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("gross_cod", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deductions_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_expected", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("bank_credit_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("utr", sa.String(length=120), nullable=True),
        sa.Column("bank_credit_date", sa.Date(), nullable=True),
        sa.Column("bank_account_ref", sa.String(length=120), nullable=True),
        sa.Column("difference", sa.Numeric(12, 2), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=4000), nullable=True),
        sa.Column("raw_meta", sa.JSON(), nullable=False),
        sa.Column("imported_by", sa.Uuid(), nullable=True),
        sa.Column("reconciled_by", sa.Uuid(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["imported_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reconciled_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cod_remittances_crf_id", "cod_remittances", ["crf_id"], unique=True)
    op.create_index("ix_cod_remittances_status", "cod_remittances", ["status"], unique=False)
    op.create_index("ix_cod_remittances_utr", "cod_remittances", ["utr"], unique=False)
    op.create_index("ix_cod_remittances_created_at", "cod_remittances", ["created_at"], unique=False)

    op.create_table(
        "cod_remittance_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("remittance_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("awb", sa.String(length=120), nullable=True),
        sa.Column("order_ref", sa.String(length=120), nullable=True),
        sa.Column("cod_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("deductions", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("remitted_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("match_status", sa.String(length=30), nullable=False),
        sa.Column("match_note", sa.String(length=500), nullable=True),
        sa.Column("line_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_row", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["remittance_id"], ["cod_remittances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("remittance_id", "line_hash", name="uq_cod_remittance_line"),
    )
    op.create_index("ix_cod_remittance_items_remittance_id", "cod_remittance_items", ["remittance_id"], unique=False)
    op.create_index("ix_cod_remittance_items_order_id", "cod_remittance_items", ["order_id"], unique=False)
    op.create_index("ix_cod_remittance_items_awb", "cod_remittance_items", ["awb"], unique=False)
    op.create_index("ix_cod_remittance_items_match_status", "cod_remittance_items", ["match_status"], unique=False)

    op.add_column(
        "orders",
        sa.Column("cod_remitted_amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "orders",
        sa.Column("cod_remittance_status", sa.String(length=20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "orders",
        sa.Column("cod_remitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_cod_remittance_status", "orders", ["cod_remittance_status"], unique=False)

    # Permission catalog + grants (idempotent, mirrors c1d2e3f4a5b6).
    conn = op.get_bind()
    existing_keys = {
        row[0] for row in conn.execute(sa.text("SELECT key FROM permissions"))
    }
    for key, label, module, description in PERMISSIONS:
        if key not in NEW_KEYS or key in existing_keys:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO permissions (id, key, label, module, description, created_at) "
                "VALUES (gen_random_uuid(), :key, :label, :module, :description, now())"
            ),
            {"key": key, "label": label, "module": module, "description": description},
        )

    perm_ids = {
        row[0]: row[1]
        for row in conn.execute(sa.text("SELECT key, id FROM permissions"))
        if row[0] in NEW_KEYS
    }
    for slug, spec in SYSTEM_ROLES.items():
        role_id = conn.execute(
            sa.text("SELECT id FROM roles WHERE slug = :slug"), {"slug": slug}
        ).scalar()
        if role_id is None:
            continue
        for key in NEW_KEYS:
            if key not in spec["permissions"]:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, granted_at) "
                    "VALUES (:role_id, :perm_id, now()) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"role_id": role_id, "perm_id": perm_ids[key]},
            )


def downgrade() -> None:
    conn = op.get_bind()
    perm_ids = [
        row[0]
        for row in conn.execute(sa.text("SELECT id, key FROM permissions"))
        if row[1] in NEW_KEYS
    ]
    for perm_id in perm_ids:
        conn.execute(
            sa.text("DELETE FROM role_permissions WHERE permission_id = :perm_id"),
            {"perm_id": perm_id},
        )
        conn.execute(
            sa.text("DELETE FROM permissions WHERE id = :perm_id"),
            {"perm_id": perm_id},
        )

    op.drop_index("ix_orders_cod_remittance_status", table_name="orders")
    op.drop_column("orders", "cod_remitted_at")
    op.drop_column("orders", "cod_remittance_status")
    op.drop_column("orders", "cod_remitted_amount")

    op.drop_index("ix_cod_remittance_items_match_status", table_name="cod_remittance_items")
    op.drop_index("ix_cod_remittance_items_awb", table_name="cod_remittance_items")
    op.drop_index("ix_cod_remittance_items_order_id", table_name="cod_remittance_items")
    op.drop_index("ix_cod_remittance_items_remittance_id", table_name="cod_remittance_items")
    op.drop_table("cod_remittance_items")

    op.drop_index("ix_cod_remittances_created_at", table_name="cod_remittances")
    op.drop_index("ix_cod_remittances_utr", table_name="cod_remittances")
    op.drop_index("ix_cod_remittances_status", table_name="cod_remittances")
    op.drop_index("ix_cod_remittances_crf_id", table_name="cod_remittances")
    op.drop_table("cod_remittances")
