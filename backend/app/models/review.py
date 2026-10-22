# app/models/review.py
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Review(SQLModel, table=True):
    __tablename__ = "reviews"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True, nullable=True)

    rating: int = Field(ge=1, le=5)
    title: str | None = None
    comment: str | None = None

    is_verified_purchase: bool = Field(default=False)  # 👈 new

    # Moderation: hidden reviews stay in the DB (audit trail) but are
    # excluded from every storefront read path (list, averages, stats).
    is_hidden: bool = Field(default=False, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )

    product: "Product" = Relationship(back_populates="reviews")
    user: "User" = Relationship(back_populates="reviews")
    order: "Order" = Relationship(back_populates="reviews")