"""Seed product/inventory MCP permissions (products.manage_prices, inventory.adjust).

Revision ID: c1d2e3f4a5b6
Revises: y0a1b2c3d4e5
Create Date: 2026-10-09

ROLLOUT ORDER (read this before deploying):
  1. Deploy code first: app/core/rbac_catalog.py already lists the two new
     keys, so SYSTEM_ROLES is the source of truth on every boot.
  2. Run `alembic upgrade head` in each environment (dev/staging/prod).
     This migration is idempotent: it only INSERTs missing permission rows
     and missing manager/admin grants, and never removes custom grants.
  3. Local dev alternative (no migratons needed): `uv run python scripts/seed_rbac.py`
     imports the same catalog and performs the same idempotent sync.
  4. Verify: SELECT key FROM permissions WHERE key IN
     ('products.manage_prices','inventory.adjust') must return 2 rows, and
     the manager role must hold both grants while staff holds neither.
  5. Rollback: `alembic downgrade -1` removes exactly these two grants/rows.

- Adds the permission rows (skipped when already present).
- Grants them to the system roles whose SYSTEM_ROLES spec includes them
  (admin = everything, manager = both new keys; staff/customer untouched).
- Staff intentionally does NOT receive them: MCP price/stock writes stay
  least-privilege even though staff keeps products.update on REST routes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'y0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_KEYS = ('products.manage_prices', 'inventory.adjust')


def upgrade() -> None:
    """Upgrade schema (data-only, idempotent)."""
    conn = op.get_bind()

    existing_keys = {
        row[0] for row in conn.execute(sa.text('SELECT key FROM permissions'))
    }
    for key, label, module, description in PERMISSIONS:
        if key not in NEW_KEYS or key in existing_keys:
            continue
        conn.execute(
            sa.text(
                'INSERT INTO permissions (id, key, label, module, description, created_at) '
                'VALUES (gen_random_uuid(), :key, :label, :module, :description, now())'
            ),
            {'key': key, 'label': label, 'module': module, 'description': description},
        )

    perm_ids = {
        row[0]: row[1]
        for row in conn.execute(sa.text('SELECT key, id FROM permissions'))
        if row[0] in NEW_KEYS
    }
    for slug, spec in SYSTEM_ROLES.items():
        role_id = conn.execute(
            sa.text('SELECT id FROM roles WHERE slug = :slug'), {'slug': slug}
        ).scalar()
        if role_id is None:
            continue
        for key in NEW_KEYS:
            if key not in spec['permissions']:
                continue
            conn.execute(
                sa.text(
                    'INSERT INTO role_permissions (role_id, permission_id, granted_at) '
                    'VALUES (:role_id, :perm_id, now()) '
                    'ON CONFLICT DO NOTHING'
                ),
                {'role_id': role_id, 'perm_id': perm_ids[key]},
            )


def downgrade() -> None:
    """Downgrade: remove exactly the grants/rows this migration adds."""
    conn = op.get_bind()
    perm_ids = [
        row[0]
        for row in conn.execute(sa.text('SELECT id, key FROM permissions'))
        if row[1] in NEW_KEYS
    ]
    for perm_id in perm_ids:
        conn.execute(
            sa.text('DELETE FROM role_permissions WHERE permission_id = :perm_id'),
            {'perm_id': perm_id},
        )
        conn.execute(
            sa.text('DELETE FROM permissions WHERE id = :perm_id'),
            {'perm_id': perm_id},
        )
