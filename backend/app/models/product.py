from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, JSON, Numeric
from sqlmodel import Field, Relationship, SQLModel
from app.models.product_image import ProductImage

class Product(SQLModel, table=True):
    __tablename__ = "products"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True
    )

    name: str = Field(
        min_length=1,
        max_length=150,
        index=True
    )

    slug: str = Field(
        max_length=180,
        unique=True,
        index=True
    )

    description: str | None = None

    category_id: UUID | None = Field(
        default=None,
        foreign_key="categories.id",
        index=True
    )

    category: "Category" = Relationship(
        back_populates="products"
    )

    # Base/default product price.
    # A variant can override this using price_override.
    price: Decimal = Field(
        gt=0,
        sa_column=Column(
            Numeric(12, 2),
            nullable=False
        )
    )

    compare_at_price: Decimal | None = Field(
        default=None,
        gt=0,
        sa_column=Column(
            Numeric(12, 2),
            nullable=True
        )
    )

    is_active: bool = Field(
        default=True,
        index=True
    )

    created_by: UUID | None = Field(
        default=None,
        foreign_key="users.id"
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False
        )
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False,
            onupdate=lambda: datetime.now(timezone.utc)
        )
    )

    # 👇 Relationship to variants
    variants: list["ProductVariant"] = Relationship(
        back_populates="product"
    )
    images: list["ProductImage"] = Relationship(back_populates="product")
    # app/models/product.py - Add to Product class
    reviews: list["Review"] = Relationship(back_populates="product")
    wishlist: list["Wishlist"] = Relationship(back_populates="product")


class ProductVariant(SQLModel, table=True):
    __tablename__ = "product_variants"

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True
    )

    product_id: UUID = Field(
        foreign_key="products.id",
        index=True
    )

    # Every purchasable variant gets its own SKU.
    sku: str = Field(
        min_length=1,
        max_length=100,
        unique=True,
        index=True
    )

    # Examples:
    # {"size": "M", "color": "Black"}
    # {"weight": "5kg"}
    # {"volume": "100ml"}
    # {"ram": "16GB", "storage": "1TB"}
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(
            JSON,
            nullable=False
        )
    )

    # If NULL, use Product.price.
    price_override: Decimal | None = Field(
        default=None,
        gt=0,
        sa_column=Column(
            Numeric(12, 2),
            nullable=True
        )
    )

    stock: int = Field(
        default=0,
        ge=0
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(
            DateTime(timezone=True),
            nullable=False
        )
    )

    # 👇 Relationship back to product
    product: Product = Relationship(
        back_populates="variants"
    )
    cart_items: list["CartItem"] = Relationship(
        back_populates="variant"
    )
    # In ProductVariant class, add:
    order_items: list["OrderItem"] = Relationship(back_populates="variant")