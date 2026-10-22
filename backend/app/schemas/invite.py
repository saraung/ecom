# app/schemas/invite.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class InviteCreate(BaseModel):
    email: EmailStr
    role_slugs: list[str]
    full_name: str | None = None

    @field_validator("role_slugs")
    @classmethod
    def at_least_one(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one role is required")
        return v


class InviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role_slugs: list[str]
    status: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InviteAcceptPreview(BaseModel):
    """Public pre-check: is this invite link live, and for whom?"""

    valid: bool
    email: str | None = None
    role_slugs: list[str] = []
    message: str | None = None


class InviteAcceptRequest(BaseModel):
    """Accept an invite.

    - New staffer: token + username + password (+ optional full_name).
      The emailed single-use link IS the email verification.
    - Existing account: call authenticated with the matching email and
      omit password fields to link the invited roles.
    """

    token: str
    username: str | None = None
    password: str | None = None
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str | None) -> str | None:
        if v and not v.replace("_", "").isalnum():
            raise ValueError(
                "Username must contain only letters, numbers, and underscores"
            )
        return v
