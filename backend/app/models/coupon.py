from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class DiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class CouponType(str, Enum):
    """How a coupon reaches the customer's cart.

    - MANUAL: the customer types the code at checkout (existing flow).
    - AUTOMATIC: the backend applies the coupon by itself when the
      configured trigger condition is met — no code entry involved.
    """

    MANUAL = "manual"
    AUTOMATIC = "automatic"


class TriggerType(str, Enum):
    """Trigger conditions that make an AUTOMATIC coupon apply itself."""

    NONE = "none"
    MIN_CART_VALUE = "min_cart_value"
    MIN_ITEM_COUNT = "min_item_count"
    CATEGORY_SPEND = "category_spend"
    FIRST_ORDER = "first_order"


class Coupon(SQLModel, table=True):
    __tablename__ = "coupons"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(unique=True, index=True, max_length=50)
    discount_type: DiscountType = Field(default=DiscountType.PERCENTAGE)
    value: Decimal = Field(max_digits=12, decimal_places=2)

    # Manual vs automatic
    coupon_type: CouponType = Field(default=CouponType.MANUAL)

    # Trigger configuration (only meaningful for AUTOMATIC coupons)
    trigger_type: TriggerType = Field(default=TriggerType.NONE)
    trigger_min_cart_value: Decimal | None = Field(
        default=None,
        max_digits=12,
        decimal_places=2,
    )
    trigger_min_item_count: int | None = None
    trigger_category_id: UUID | None = Field(
        default=None,
        foreign_key="categories.id",
    )
    trigger_category_spend: Decimal | None = Field(
        default=None,
        max_digits=12,
        decimal_places=2,
    )

    min_order_value: Decimal | None = Field(
        default=None, 
        max_digits=12, 
        decimal_places=2
    )
    # Internal/test codes are rejected at checkout validation — staff comps
    # and QA codes can never leak onto public orders.
    internal_only: bool = Field(default=False, index=True)
    max_uses: int | None = None
    max_uses_per_user: int = Field(default=1)
    times_used: int = Field(default=0)
    
    valid_from: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    valid_until: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    is_active: bool = Field(default=True)
    
    created_by: UUID = Field(foreign_key="users.id")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )
    
    # Relationships
    creator: "User" = Relationship(back_populates="coupons")
