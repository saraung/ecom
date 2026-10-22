# app/schemas/notification.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    title: str
    message: str | None
    link: str | None
    order_id: UUID | None
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationRead]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    updated: int


class DeleteResponse(BaseModel):
    ok: bool


class PromotionBroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    link: str | None = Field(default=None, max_length=300)
    # Email fan-out is opt-in per send (defaults to feed-only, the historic
    # behaviour). Recipients are the feed audience further gated on each
    # user's Email Notifications toggle; staff never receive promos.
    send_email: bool = False


class PromotionBroadcastResponse(BaseModel):
    broadcast_id: UUID
    title: str
    message: str
    link: str | None
    recipients_count: int
    # Recipients queued for background email delivery (0 when send_email
    # was false — emails are counted as sent/failed in history instead).
    emails_queued: int = 0
    created_at: datetime


class PromotionHistoryItem(BaseModel):
    id: UUID
    title: str
    message: str | None
    link: str | None
    recipients_count: int
    email_requested: bool = False
    emails_sent: int = 0
    emails_failed: int = 0
    created_at: datetime


class PromotionRetractResponse(BaseModel):
    deleted_count: int


class PromotionAudienceEstimate(BaseModel):
    feed_recipients: int
    email_recipients: int