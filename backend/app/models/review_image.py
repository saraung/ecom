from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index
from sqlmodel import Field, SQLModel


class ReviewImage(SQLModel, table=True):
    __tablename__ = "review_images"
    __table_args__ = (Index("ix_review_images_cloudinary_public_id", "cloudinary_public_id"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    review_id: UUID = Field(foreign_key="reviews.id", index=True)
    secure_url: str = Field(max_length=1000)
    cloudinary_public_id: str = Field(max_length=500, unique=True)
    filename: str = Field(max_length=160)
    sort_order: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True))
