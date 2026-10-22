from decimal import Decimal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


# -------------------------
# Request Schemas
# -------------------------

class AddToCartRequest(BaseModel):
    variant_id: UUID
    quantity: int = Field(ge=1, le=999)
    merge_key: UUID | None = None


class UpdateCartItemRequest(BaseModel):
    quantity: int = Field(ge=1, le=999)


# -------------------------
# Response Schemas
# -------------------------

class CartItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    variant_id: UUID
    quantity: int
    price_at_add: Decimal
    created_at: datetime
    
    # Additional fields from variant/product (optional)
    variant_sku: str | None = None
    variant_attributes: dict | None = None
    product_name: str | None = None
    product_slug: str | None = None
    product_image: str | None = None


class AutomaticCouponRead(BaseModel):
    """Server-decided automatic coupon for the storefront (display only).

    The backend evaluates every trigger and decides whether this coupon
    applies and how much it is worth — the frontend only renders it.
    """

    code: str
    discount_type: str
    value: Decimal
    discount_amount: Decimal
    trigger_type: str
    description: str


class CartRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    items: list[CartItemRead] = Field(default_factory=list)
    subtotal: Decimal = Field(default=Decimal("0.00"))
    coupon_code: str | None = None
    automatic_coupon: AutomaticCouponRead | None = None
    discount_total: Decimal = Field(default=Decimal("0.00"))
    tax_total: Decimal = Field(default=Decimal("0.00"))
    shipping_total: Decimal = Field(default=Decimal("0.00"))
    total: Decimal = Field(default=Decimal("0.00"))
    item_count: int = Field(default=0)

class ApplyCouponRequest(BaseModel):
    coupon_code: str = Field(min_length=1, max_length=50)
