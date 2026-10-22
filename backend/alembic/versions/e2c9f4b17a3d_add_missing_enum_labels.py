"""Add missing enum labels (orderstatus.OUT_FOR_DELIVERY / orderstatus.RTO / paymentprovider.COD)

The Python models gained `OrderStatus.OUT_FOR_DELIVERY`, `OrderStatus.RTO` and
`PaymentProvider.COD`, but the Postgres enum types were never widened. SQLAlchemy
persists the enum member *name* (not its value) for a PEP-435 enum, so writing any
of those three members raised:

    InvalidTextRepresentation: invalid input value for enum orderstatus: "OUT_FOR_DELIVERY"

which surfaces as an HTTP 500 on:

- POST /api/v1/admin/orders/{id}/shipping/simulator/trigger-event  ("out_for_delivery", "rto")
- POST /api/v1/webhooks/shiprocket                                 ("out_for_delivery" / RTO scans)
- PUT  /api/v1/admin/orders/{id}/status                            (manual status change)
- COD payment recording, which uses PaymentProvider.COD

Revision ID: e2c9f4b17a3d
Revises: d93077abdc18
Create Date: 2026-09-25 15:55:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e2c9f4b17a3d'
down_revision: Union[str, Sequence[str], None] = 'd93077abdc18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (postgres type name, label) pairs that exist in the Python enums but not in the DB
_MISSING_ENUM_LABELS: tuple[tuple[str, str], ...] = (
    ('orderstatus', 'OUT_FOR_DELIVERY'),
    ('orderstatus', 'RTO'),
    ('paymentprovider', 'COD'),
)


def upgrade() -> None:
    """Upgrade schema."""
    if op.get_bind().dialect.name != 'postgresql':
        # SQLite (used by the test suite) stores enums as VARCHAR with a CHECK
        # constraint generated from the current models, so there is nothing to widen.
        return

    # `ALTER TYPE ... ADD VALUE` must run outside a transaction block.
    with op.get_context().autocommit_block():
        for type_name, label in _MISSING_ENUM_LABELS:
            op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    """Downgrade schema."""
    # NOTE: PostgreSQL cannot remove enum values, so the labels added above are
    # intentionally left in place on downgrade.
    pass
