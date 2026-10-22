"""Add missing enum label notificationtype.REFUND_APPROVAL

The Python model gained `NotificationType.REFUND_APPROVAL` (staff-only alert: a
staged refund needs a second admin's decision), but the Postgres enum type was
never widened. SQLAlchemy persists the enum member *name* (not its value) for a
PEP-435 enum, so every statement that touches this member raised:

    InvalidTextRepresentation: invalid input value for enum notificationtype: "REFUND_APPROVAL"

which surfaced as an HTTP 500 on the whole admin notification feed, because
`STAFF_NOTIFICATION_TYPES` includes REFUND_APPROVAL and the admin panel always
sends `audience=staff`:

- GET /api/v1/notifications?audience=staff            -> 500  (bell feed empty)
- GET /api/v1/notifications/unread-count?audience=staff -> 500 (badge always 0)
- PUT /api/v1/notifications/mark-all-read?audience=staff -> 500
- staging a refund via POST /api/v1/admin/orders/{id}/refunds (insert failed)

Revision ID: h3d4e5f6a7b8
Revises: g2b3c4d5e6f7
Create Date: 2026-09-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'h3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'g2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (postgres type name, label) pairs that exist in the Python enums but not in the DB
_MISSING_ENUM_LABELS: tuple[tuple[str, str], ...] = (
    ('notificationtype', 'REFUND_APPROVAL'),
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        # SQLite (used by the test suite) stores enums as VARCHAR with a CHECK
        # constraint generated from the current models, so there is nothing to widen.
        return

    # Older databases created the column as a plain VARCHAR (see revision
    # d4e5f6a7b8c9); only widen the enum when the native type actually exists.
    type_exists = bind.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = 'notificationtype'")
    ).first()
    if type_exists is None:
        return

    # `ALTER TYPE ... ADD VALUE` must run outside a transaction block.
    with op.get_context().autocommit_block():
        for type_name, label in _MISSING_ENUM_LABELS:
            op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{label}'")


def downgrade() -> None:
    """Downgrade schema."""
    # NOTE: PostgreSQL cannot remove enum values, so the label added above is
    # intentionally left in place on downgrade.
    pass
