# app/models/rbac.py
"""Dynamic RBAC tables for single-tenant mode (tenant-ready).

Design decisions (single-tenant Phase 1):
- ``Permission`` rows are the global catalog. They are seeded by migrations /
  the seed script — the admin UI only *assigns* them to roles, it never
  creates new permission keys.
- ``Role`` rows are created/managed by the admin from the dashboard.
  ``tenant_id`` is NULL today (single tenant) and becomes the scoping column
  when multi-tenancy is introduced later — no schema rework needed then.
- ``User.role`` (legacy enum) is kept as a deprecated display/backfill field.
  The source of truth for authorization is ``user_roles`` + ``role_permissions``.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # e.g. "orders.refund", "products.create"
    key: str = Field(max_length=100, unique=True, index=True)
    label: str = Field(max_length=150)
    # e.g. "products", "orders", "users"
    module: str = Field(max_length=50, index=True)
    description: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # NULL in single-tenant mode; reserved for future multi-tenant scoping.
    tenant_id: UUID | None = Field(default=None, index=True)
    name: str = Field(max_length=100)
    # unique per tenant once multi-tenancy lands; unique globally for now
    # (enforced at the repository level to keep the migration simple).
    slug: str = Field(max_length=100, unique=True, index=True)
    description: str | None = Field(default=None, max_length=500)
    # System roles (admin/manager/staff/customer) cannot be deleted,
    # only their permission sets can be edited.
    is_system: bool = Field(default=False)
    # Max single-refund amount this role may execute WITHOUT a second
    # admin's approval. None = unlimited. Above-limit (or self-order)
    # refunds become pending_approval rows instead of executing.
    max_refund_amount: Decimal | None = Field(
        default=None, max_digits=12, decimal_places=2
    )
    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RolePermissionLink(SQLModel, table=True):
    __tablename__ = "role_permissions"

    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)
    permission_id: UUID = Field(
        foreign_key="permissions.id", primary_key=True
    )
    granted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class UserRoleLink(SQLModel, table=True):
    __tablename__ = "user_roles"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)
    role_id: UUID = Field(foreign_key="roles.id", primary_key=True)
    assigned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    assigned_by: UUID | None = Field(
        default=None, foreign_key="users.id"
    )
