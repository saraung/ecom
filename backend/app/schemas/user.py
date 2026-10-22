import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator, ConfigDict

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        # 👇 Allow letters, numbers, and underscore
        if not v.replace('_', '').isalnum():
            raise ValueError("Username must contain only letters, numbers, and underscores")
        return v


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: uuid.UUID
    email: EmailStr
    username: str
    role: UserRole
    # Dynamic RBAC: populated by /auth/me from user_roles + grants.
    # Defaults keep old clients working when the RBAC tables are missing.
    roles: list[str] = []
    permissions: list[str] = []
    full_name: str | None
    phone: str | None
    is_active: bool
    email_verified: bool
    auth_provider: str = "email"
    push_notifications_enabled: bool = True
    email_notifications_enabled: bool = True
    created_at: datetime
    updated_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    # Which API this login is for. "admin" (default) keeps the OTP step-up for
    # privileged accounts; "storefront" issues a customer-scoped session so
    # staff can shop without weakening the admin gate.
    audience: Literal["admin", "storefront"] = "admin"


class SetPasswordRequest(BaseModel):
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdateProfile(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    username: str | None = None
    push_notifications_enabled: bool | None = None
    email_notifications_enabled: bool | None = None

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if v:
            # 👇 Allow letters, numbers, and underscores
            if not v.replace('_', '').isalnum():
                raise ValueError("Username must contain only letters, numbers, and underscores")
        return v