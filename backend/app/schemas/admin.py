from uuid import UUID
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, ConfigDict

from app.models.user import UserRole


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    full_name: str | None = None
    phone: str | None = None


class AdminUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    email: EmailStr
    username: str
    role: UserRole
    # Dynamic RBAC role slugs (populated from user_roles).
    roles: list[str] = []
    permissions: list[str] = []
    full_name: str | None
    phone: str | None
    is_active: bool
    email_verified: bool
    auth_provider: str
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    users: list[AdminUserRead]
    total: int
    page: int
    limit: int
    total_pages: int


class AdminUserStats(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    admin_users: int
    staff_users: int
    manager_users: int
    customer_users: int
    google_users: int
    email_users: int
    both_users: int


class AdminUserOrderStats(BaseModel):
    user_id: UUID
    total_orders: int
    total_spent: float
    gross_total: float
    refunded_total: float
    average_order_value: float
    total_items_purchased: int
    first_order: datetime | None
    last_order: datetime | None
    status_breakdown: dict[str, int]
    most_ordered_product: str | None