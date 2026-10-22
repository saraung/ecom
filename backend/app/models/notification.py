# app/models/notification.py
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class NotificationType(str, Enum):
    ORDER_PLACED = "order_placed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_STATUS = "order_status"
    PROMOTION = "promotion"
    # Staff-only: a refund is staged and needs a second admin's decision.
    # ⚠️ Adding a member here requires a matching `ALTER TYPE notificationtype
    # ADD VALUE '<MEMBER_NAME>'` migration: SQLAlchemy persists the member NAME
    # (e.g. "REFUND_APPROVAL") into the native Postgres enum, so a new member
    # whose label is missing from the DB makes any query/insert touching it
    # fail with InvalidTextRepresentation (HTTP 500). See revision h3d4e5f6a7b8.
    REFUND_APPROVAL = "refund_approval"


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)

    type: NotificationType = Field(index=True)
    title: str
    message: str | None = None
    link: str | None = None
    order_id: UUID | None = Field(default=None, index=True)

    # 👇 Groups every row created by one promotional broadcast (history view)
    broadcast_id: UUID | None = Field(default=None, index=True)

    is_read: bool = Field(default=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class PromotionBroadcast(SQLModel, table=True):
    """Header row for one promotional broadcast (feed + optional email).

    Feed rows in ``notifications`` carry the same ``id`` as their
    ``broadcast_id``; email sends produce no feed rows, so their outcome
    (``emails_sent`` / ``emails_failed``) lives here. History reads this
    table first and falls back to grouping legacy feed rows for broadcasts
    that predate it. Retracting a broadcast deletes its feed rows AND this
    header, matching the historic "vanishes from history" behaviour.
    """

    __tablename__ = "promotion_broadcasts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    title: str
    message: str | None = None
    link: str | None = None
    recipients_count: int = Field(default=0)
    email_requested: bool = Field(default=False)
    emails_sent: int = Field(default=0)
    emails_failed: int = Field(default=0)
    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )