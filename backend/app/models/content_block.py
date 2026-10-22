# app/models/content_block.py
"""Storefront content blocks (announcement bar, hero, promos).

V1 scope is deliberately narrow: keyed slots, not a page builder.
Well-known keys (documented in the admin UI, enforced nowhere):
  - ``announcement.bar`` — thin top strip store-wide
  - ``home.hero`` — homepage headline + subcopy + CTA

``key`` is unique; at most one block renders per slot. Publish windows
(``starts_at``/``ends_at``) let campaigns auto-appear/expire; null = always.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class ContentBlock(SQLModel, table=True):
    __tablename__ = "content_blocks"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Slot this block renders in (e.g. "announcement.bar"). NOT unique:
    # a slot holds an ordered list (slider) via sort_order.
    key: str = Field(index=True, min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    body: str | None = Field(default=None, max_length=2000)
    # Existing rows are migrated with "overlay" to preserve their rendering;
    # newly authored homepage heroes default to the editorial split layout.
    layout_mode: str = Field(default="split", max_length=20)
    image_url: str | None = Field(default=None, max_length=500)
    image_public_id: str | None = Field(default=None, max_length=500)
    mobile_image_url: str | None = Field(default=None, max_length=500)
    mobile_image_public_id: str | None = Field(default=None, max_length=500)
    image_alt: str | None = Field(default=None, max_length=500)
    image_position: str = Field(default="center", max_length=20)
    link: str | None = Field(default=None, max_length=300)
    link_label: str | None = Field(default=None, max_length=60)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    starts_at: datetime | None = Field(default=None)
    ends_at: datetime | None = Field(default=None)
    created_by: UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
