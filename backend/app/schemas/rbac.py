# app/schemas/rbac.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    label: str
    module: str
    description: str | None = None


class RolePermissionRead(BaseModel):
    """Role with its granted permission keys (what the UI needs)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None = None
    name: str
    slug: str
    description: str | None = None
    is_system: bool = False
    # Max single-refund auto-approval amount. None = unlimited.
    max_refund_amount: Decimal | None = None
    permissions: list[str] = []
    user_count: int = 0
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    permission_keys: list[str] = []
    # None = unlimited (admin default). Omit for system-seeded values.
    max_refund_amount: Decimal | None = Field(default=None, ge=0)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Role name is required")
        if len(v) > 100:
            raise ValueError("Role name must be at most 100 characters")
        return v.strip()

    @field_validator("slug")
    @classmethod
    def slug_normalize(cls, v: str | None) -> str | None:
        if v is None:
            return v
        slug = v.strip().lower().replace(" ", "-")
        if not slug:
            raise ValueError("Role slug cannot be empty")
        if len(slug) > 100:
            raise ValueError("Role slug must be at most 100 characters")
        if not slug.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Role slug may only contain letters, numbers, '-' and '_'"
            )
        return slug


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    # When provided, REPLACES the full permission set.
    permission_keys: list[str] | None = None
    # Max auto-approvable single refund (None = unlimited). The endpoint
    # checks model_fields_set so explicit null clears while omission keeps.
    max_refund_amount: Decimal | None = Field(default=None, ge=0)


class UserRolesUpdate(BaseModel):
    """Replace a user's role set (admin assigns roles, not raw permissions)."""

    role_slugs: list[str]

    @field_validator("role_slugs")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one role is required")
        return v
