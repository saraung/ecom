# app/models/staff_invite.py
"""Staff invitation flow (replaces "sign up, then promote").

- Admin creates an invite (email + role slugs); the invitee gets a link.
- Token is single-use, hashed at rest, 7-day expiry.
- Accepting with an existing account links it; new accounts register with
  the email locked and receive the invited roles automatically.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class StaffInviteStatus(str):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class StaffInvite(SQLModel, table=True):
    __tablename__ = "staff_invites"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(max_length=255, index=True)
    role_slugs: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    invited_by: UUID | None = Field(
        default=None, foreign_key="users.id"
    )
    # SHA-256 hex of the single-use token.
    token_hash: str = Field(max_length=128, unique=True, index=True)
    status: str = Field(default=StaffInviteStatus.PENDING, index=True)
    expires_at: datetime = Field()
    accepted_at: datetime | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
