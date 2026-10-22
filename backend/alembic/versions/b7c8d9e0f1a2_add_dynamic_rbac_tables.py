"""Add dynamic RBAC tables (permissions, roles, grants, assignments).

Revision ID: b7c8d9e0f1a2
Revises: f4a2c9d17e55
Create Date: 2026-09-28

- Creates permissions / roles / role_permissions / user_roles.
- Seeds the permission catalog + 4 system roles (admin/manager/staff/
  customer) mirroring the legacy require_role hierarchy.
- Backfills user_roles from the legacy users.role enum.
- The legacy users.role column is intentionally KEPT (deprecated display
  field, kept in sync) so old clients keep working.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'f4a2c9d17e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'permissions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('label', sa.String(length=150), nullable=False),
        sa.Column('module', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_permissions_key', 'permissions', ['key'], unique=True)
    op.create_index('ix_permissions_module', 'permissions', ['module'], unique=False)

    op.create_table(
        'roles',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tenant_id', sa.Uuid(), nullable=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_roles_slug', 'roles', ['slug'], unique=True)
    op.create_index('ix_roles_tenant_id', 'roles', ['tenant_id'], unique=False)

    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Uuid(), nullable=False),
        sa.Column('permission_id', sa.Uuid(), nullable=False),
        sa.Column('granted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('role_id', sa.Uuid(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=False),
        sa.Column('assigned_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_by'], ['users.id']),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
    )

    # --- Seed catalog + system roles + backfill (idempotent) --------------
    conn = op.get_bind()

    existing_keys = {
        row[0] for row in conn.execute(sa.text('SELECT key FROM permissions'))
    }
    for key, label, module, description in PERMISSIONS:
        if key in existing_keys:
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
    }
    existing_roles = {
        row[0] for row in conn.execute(sa.text('SELECT slug FROM roles'))
    }
    for slug, spec in SYSTEM_ROLES.items():
        if slug in existing_roles:
            role_id = conn.execute(
                sa.text('SELECT id FROM roles WHERE slug = :slug'), {'slug': slug}
            ).scalar()
        else:
            role_id = conn.execute(
                sa.text(
                    'INSERT INTO roles (id, tenant_id, name, slug, description, '
                    'is_system, created_by, created_at, updated_at) '
                    "VALUES (gen_random_uuid(), NULL, :name, :slug, :description, "
                    'true, NULL, now(), now()) RETURNING id'
                ),
                {'name': spec['name'], 'slug': slug, 'description': spec['description']},
            ).scalar()
        # Sync grants to the catalog snapshot.
        current = {
            row[0]
            for row in conn.execute(
                sa.text(
                    'SELECT p.key FROM role_permissions rp '
                    'JOIN permissions p ON p.id = rp.permission_id '
                    'WHERE rp.role_id = :role_id'
                ),
                {'role_id': role_id},
            )
        }
        wanted = set(spec['permissions'])
        for key in wanted - current:
            conn.execute(
                sa.text(
                    'INSERT INTO role_permissions (role_id, permission_id, granted_at) '
                    'VALUES (:role_id, :perm_id, now()) '
                    'ON CONFLICT DO NOTHING'
                ),
                {'role_id': role_id, 'perm_id': perm_ids[key]},
            )
        for key in current - wanted:
            conn.execute(
                sa.text(
                    'DELETE FROM role_permissions '
                    'WHERE role_id = :role_id AND permission_id = :perm_id'
                ),
                {'role_id': role_id, 'perm_id': perm_ids[key]},
            )

    # Backfill user_roles from legacy users.role (users without any link).
    conn.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id, assigned_at, assigned_by) "
            "SELECT u.id, r.id, now(), NULL FROM users u "
            "JOIN roles r ON r.slug = lower(u.role::text) "
            "LEFT JOIN user_roles ur ON ur.user_id = u.id "
            "WHERE ur.user_id IS NULL "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_roles')
    op.drop_table('role_permissions')
    op.drop_index('ix_roles_tenant_id', table_name='roles')
    op.drop_index('ix_roles_slug', table_name='roles')
    op.drop_table('roles')
    op.drop_index('ix_permissions_module', table_name='permissions')
    op.drop_index('ix_permissions_key', table_name='permissions')
    op.drop_table('permissions')
