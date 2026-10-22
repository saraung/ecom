"""Guardrails: refund ledger, audit log, invites, staff flags, coupon + role limits.

Revision ID: e8f9a0b1c2d3
Revises: c8d9e0f1a2b3
Create Date: 2026-09-28

- New tables: refunds, admin_audit_log, staff_invites.
- roles.max_refund_amount (manager 5000, staff/customer 0, admin unlimited).
- orders.placed_by_staff (backfilled from current role grants).
- coupons.internal_only (default false).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'refunds',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('restocking_fee', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('idempotency_key', sa.String(length=100), nullable=False),
        sa.Column('status', sa.Enum(
            'PENDING_APPROVAL', 'EXECUTED', 'REJECTED', 'FAILED',
            name='refundstatus',
        ), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('requested_by', sa.Uuid(), nullable=True),
        sa.Column('approved_by', sa.Uuid(), nullable=True),
        sa.Column('provider_refund_id', sa.String(), nullable=True),
        sa.Column('provider_status', sa.String(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by'], ['users.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refunds_idempotency_key', 'refunds', ['idempotency_key'], unique=True)
    op.create_index('ix_refunds_order_id', 'refunds', ['order_id'], unique=False)
    op.create_index('ix_refunds_status', 'refunds', ['status'], unique=False)
    op.create_index('ix_refunds_provider_refund_id', 'refunds', ['provider_refund_id'], unique=False)

    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('actor_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('before', sa.JSON(), nullable=True),
        sa.Column('after', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_admin_audit_actor', 'admin_audit_log', ['actor_id'], unique=False)
    op.create_index('ix_admin_audit_action', 'admin_audit_log', ['action'], unique=False)
    op.create_index('ix_admin_audit_entity', 'admin_audit_log', ['entity', 'entity_id'], unique=False)
    op.create_index('ix_admin_audit_created', 'admin_audit_log', ['created_at'], unique=False)

    op.create_table(
        'staff_invites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role_slugs', sa.JSON(), nullable=False),
        sa.Column('invited_by', sa.Uuid(), nullable=True),
        sa.Column('token_hash', sa.String(length=128), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_staff_invites_email', 'staff_invites', ['email'], unique=False)
    op.create_index('ix_staff_invites_token', 'staff_invites', ['token_hash'], unique=True)
    op.create_index('ix_staff_invites_status', 'staff_invites', ['status'], unique=False)

    op.add_column('roles', sa.Column(
        'max_refund_amount', sa.Numeric(precision=12, scale=2), nullable=True
    ))
    op.add_column('orders', sa.Column(
        'placed_by_staff', sa.Boolean(), nullable=False, server_default='false'
    ))
    op.add_column('coupons', sa.Column(
        'internal_only', sa.Boolean(), nullable=False, server_default='false'
    ))
    op.create_index('ix_orders_placed_by_staff', 'orders', ['placed_by_staff'], unique=False)
    op.create_index('ix_coupons_internal_only', 'coupons', ['internal_only'], unique=False)

    conn = op.get_bind()
    # Refund authority defaults: manager auto up to 5000, staff/customer 0
    # (they hold no refund permission anyway), admin unlimited (NULL).
    conn.execute(sa.text(
        "UPDATE roles SET max_refund_amount = 5000 "
        "WHERE slug = 'manager' AND max_refund_amount IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE roles SET max_refund_amount = 0 "
        "WHERE slug IN ('staff', 'customer') AND max_refund_amount IS NULL"
    ))
    # Backfill: orders whose buyer currently holds any granted permission.
    conn.execute(sa.text(
        "UPDATE orders SET placed_by_staff = true WHERE user_id IN ("
        "SELECT DISTINCT ur.user_id FROM user_roles ur "
        "JOIN role_permissions rp ON rp.role_id = ur.role_id)"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_coupons_internal_only', table_name='coupons')
    op.drop_index('ix_orders_placed_by_staff', table_name='orders')
    op.drop_column('coupons', 'internal_only')
    op.drop_column('orders', 'placed_by_staff')
    op.drop_column('roles', 'max_refund_amount')
    op.drop_index('ix_staff_invites_status', table_name='staff_invites')
    op.drop_index('ix_staff_invites_token', table_name='staff_invites')
    op.drop_index('ix_staff_invites_email', table_name='staff_invites')
    op.drop_table('staff_invites')
    op.drop_index('ix_admin_audit_created', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_entity', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_action', table_name='admin_audit_log')
    op.drop_index('ix_admin_audit_actor', table_name='admin_audit_log')
    op.drop_table('admin_audit_log')
    op.drop_index('ix_refunds_provider_refund_id', table_name='refunds')
    op.drop_index('ix_refunds_status', table_name='refunds')
    op.drop_index('ix_refunds_order_id', table_name='refunds')
    op.drop_index('ix_refunds_idempotency_key', table_name='refunds')
    op.drop_table('refunds')
    sa.Enum(name='refundstatus').drop(op.get_bind(), checkfirst=True)
