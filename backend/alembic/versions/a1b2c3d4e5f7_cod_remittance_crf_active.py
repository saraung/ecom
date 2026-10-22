"""Case-insensitive CRF uniqueness only while a remittance batch is active.

Revision ID: a1b2c3d4e5f7
Revises: z1b2c3d4e5f6
Create Date: 2026-10-20

``z1b2c3d4e5f6`` made ``cod_remittances.crf_id`` globally unique. That blocked
the documented "void it first to re-import" workflow because the voided row kept
occupying the reference.

This migration replaces the full unique index with:

* ``ix_cod_remittances_crf_id`` — a normal index for lookups/search;
* ``crf_key`` — ``lower(trim(crf_id))`` maintained by the service;
* ``uq_cod_remittances_crf_active`` — a partial unique index on ``crf_key``
  that only covers rows whose ``status`` is not ``void``.

The partial index is also case-insensitive, closing the race where two active
batches differ only by CRF letter case.

Downgrade restores the old global unique index. If voided batches were later
re-imported with the same CRF, their ``crf_id`` is suffixed with the row id so
the old constraint can be recreated without deleting financial history.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "z1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _active_duplicate_keys(conn) -> list[tuple[str, int]]:
    return list(
        conn.execute(
            sa.text(
                "SELECT lower(trim(crf_id)) AS key, count(*) AS total "
                "FROM cod_remittances "
                "WHERE status <> 'void' "
                "GROUP BY lower(trim(crf_id)) "
                "HAVING count(*) > 1"
            )
        ).all()
    )


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = _active_duplicate_keys(conn)
    if duplicates:
        detail = ", ".join(f"{key!r} x{total}" for key, total in duplicates[:10])
        raise RuntimeError(
            "Cannot add case-insensitive active CRF uniqueness: resolve these "
            f"duplicate active CRF references first: {detail}"
        )

    op.add_column(
        "cod_remittances",
        sa.Column("crf_key", sa.String(length=120), nullable=True),
    )
    conn.execute(
        sa.text("UPDATE cod_remittances SET crf_key = lower(trim(crf_id))")
    )
    op.alter_column(
        "cod_remittances",
        "crf_key",
        existing_type=sa.String(length=120),
        nullable=False,
    )

    op.drop_index("ix_cod_remittances_crf_id", table_name="cod_remittances")
    op.create_index(
        "ix_cod_remittances_crf_id", "cod_remittances", ["crf_id"], unique=False
    )
    op.create_index(
        "ix_cod_remittances_crf_key", "cod_remittances", ["crf_key"], unique=False
    )
    op.create_index(
        "uq_cod_remittances_crf_active",
        "cod_remittances",
        ["crf_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'void'"),
        sqlite_where=sa.text("status <> 'void'"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    duplicates = _active_duplicate_keys(conn)
    if duplicates:
        detail = ", ".join(f"{key!r} x{total}" for key, total in duplicates[:10])
        raise RuntimeError(
            "Cannot restore global CRF uniqueness while duplicate active CRF "
            f"references exist: {detail}"
        )

    # Free the reference held by voided duplicates before recreating the old
    # global unique index. Financial rows are kept, only the display reference
    # gets a deterministic suffix.
    conn.execute(
        sa.text(
            "UPDATE cod_remittances AS c "
            "SET crf_id = left(c.crf_id, 100) || ' [void ' || left(c.id::text, 8) || ']' "
            "WHERE c.status = 'void' "
            "AND EXISTS ("
            "  SELECT 1 FROM cod_remittances AS c2 "
            "  WHERE lower(trim(c2.crf_id)) = lower(trim(c.crf_id)) "
            "  AND c2.id <> c.id"
            ")"
        )
    )

    op.drop_index("uq_cod_remittances_crf_active", table_name="cod_remittances")
    op.drop_index("ix_cod_remittances_crf_key", table_name="cod_remittances")
    op.drop_column("cod_remittances", "crf_key")
    op.drop_index("ix_cod_remittances_crf_id", table_name="cod_remittances")
    op.create_index(
        "ix_cod_remittances_crf_id", "cod_remittances", ["crf_id"], unique=True
    )
