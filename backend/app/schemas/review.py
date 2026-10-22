# app/schemas/review.py
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = None
    comment: str | None = None


class ReviewUpdate(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = None
    comment: str | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    user_id: UUID
    order_id: UUID | None
    rating: int
    title: str | None
    comment: str | None
    is_verified_purchase: bool  # 👈 new
    is_hidden: bool = False
    created_at: datetime
    updated_at: datetime
    user_full_name: str | None = None
    images: list["ReviewImageRead"] = Field(default_factory=list)


class ReviewImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    review_id: UUID
    secure_url: str
    filename: str
    sort_order: int


class AdminReviewRead(ReviewRead):
    """Moderation row: storefront fields plus product + reviewer identity."""

    product_name: str | None = None
    user_email: str | None = None


class ReviewVisibilityUpdate(BaseModel):
    is_hidden: bool


class ReviewListResponse(BaseModel):
    items: list[AdminReviewRead]
    total: int
    page: int
    limit: int
    total_pages: int
