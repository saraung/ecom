from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, DateTime
from sqlmodel import SQLModel, Field


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True
    )

    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        index=True
    )

    token_hash: str = Field(
        unique=True,
        index=True
    )

    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    # Which API this session may talk to ("admin" | "storefront"). Persisted so
    # POST /auth/refresh re-issues with the SAME audience — without this a
    # storefront session would mint an admin-capable token on every refresh.
    # Defaults to "admin" so pre-existing rows keep working (they were all
    # issued through the OTP-gated admin login).
    scope: str = Field(default="admin", max_length=20, index=True)

    revoked: bool = Field(default=False)
    # Stable login identity across rotations; logout invalidates only this session.
    session_id: uuid.UUID = Field(default_factory=uuid.uuid4, index=True)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
