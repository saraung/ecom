from decimal import Decimal
from typing import Any
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.schemas.product_image import ProductImageRead


# -------------------------
# Variant schemas
# -------------------------

class ProductVariantCreate(BaseModel):
    sku: str = Field(
        min_length=1,
        max_length=100
    )

    attributes: dict[str, Any] = Field(
        default_factory=dict
    )

    price_override: Decimal | None = Field(
        default=None,
        gt=0
    )

    stock: int = Field(
        default=0,
        ge=0
    )


class ProductVariantUpdate(BaseModel):
    sku: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )

    attributes: dict[str, Any] | None = None

    price_override: Decimal | None = Field(
        default=None,
        gt=0
    )

    stock: int | None = Field(
        default=None,
        ge=0
    )


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    sku: str
    attributes: dict[str, Any]
    price_override: Decimal | None
    stock: int
    created_at: datetime
    
    # 👇 Computed fields (NOT stored in DB)
    effective_price: Decimal | None = None
    discount_percentage: int = 0
    savings_amount: Decimal = Decimal("0.00")
    is_on_sale: bool = False


# -------------------------
# Product schemas
# -------------------------

class ProductCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=150
    )

    slug: str = Field(
        min_length=1,
        max_length=180
    )

    description: str | None = None

    category_id: UUID | None = None

    price: Decimal = Field(
        gt=0
    )

    compare_at_price: Decimal | None = Field(
        default=None,
        gt=0
    )

    # Optional when creating the product.
    # A product may have no variants.
    variants: list[ProductVariantCreate] = Field(
        default_factory=list
    )


class ProductUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150
    )

    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=180
    )

    description: str | None = None

    category_id: UUID | None = None

    price: Decimal | None = Field(
        default=None,
        gt=0
    )

    compare_at_price: Decimal | None = Field(
        default=None,
        gt=0
    )

    is_active: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    category_id: UUID | None

    price: Decimal
    compare_at_price: Decimal | None

    is_active: bool

    created_by: UUID | None

    created_at: datetime
    updated_at: datetime

    variants: list[ProductVariantRead] = Field(
        default_factory=list
    )
    images: list[ProductImageRead] = Field(default_factory=list)
    
    # 👇 Computed fields (NOT stored in DB)
    discount_percentage: int = 0
    savings_amount: Decimal = Decimal("0.00")
    is_on_sale: bool = False

    # 👇 Review aggregate fields (NOT stored in DB — computed from reviews table)
    average_rating: float = 0.0
    review_count: int = 0


class ProductPage(BaseModel):
    products: list[ProductRead]
    total: int
    page: int
    limit: int
    total_pages: int
