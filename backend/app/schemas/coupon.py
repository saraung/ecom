from datetime import datetime
from decimal import Decimal
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, model_validator

from app.models.coupon import CouponType, TriggerType


class DiscountTypeEnum(str, Enum):
    PERCENTAGE = "percentage"
    FIXED = "fixed"


class CouponTypeEnum(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class TriggerTypeEnum(str, Enum):
    NONE = "none"
    MIN_CART_VALUE = "min_cart_value"
    MIN_ITEM_COUNT = "min_item_count"
    CATEGORY_SPEND = "category_spend"
    FIRST_ORDER = "first_order"


def _enum_value(field) -> str:
    """Normalize enum members / plain strings to their value."""
    return str(getattr(field, "value", field))


def validate_trigger_config(
    *,
    coupon_type,
    trigger_type,
    code: str | None = None,
    trigger_min_cart_value: Decimal | None = None,
    trigger_min_item_count: int | None = None,
    trigger_category_id: UUID | None = None,
    trigger_category_spend: Decimal | None = None,
) -> None:
    """
    Cross-field validation shared by CouponCreate, CouponUpdate and the API
    layer. Raises ValueError with a human-friendly message on bad config.
    """
    is_automatic = _enum_value(coupon_type) == CouponType.AUTOMATIC.value
    trigger = _enum_value(trigger_type)

    if is_automatic:
        if trigger == TriggerType.NONE.value:
            raise ValueError("Automatic coupons require a trigger condition")
        if trigger == TriggerType.MIN_CART_VALUE.value and trigger_min_cart_value is None:
            raise ValueError(
                "Trigger 'minimum cart value' requires trigger_min_cart_value"
            )
        if trigger == TriggerType.MIN_ITEM_COUNT.value and trigger_min_item_count is None:
            raise ValueError(
                "Trigger 'minimum item count' requires trigger_min_item_count"
            )
        if trigger == TriggerType.CATEGORY_SPEND.value and (
            trigger_category_id is None or trigger_category_spend is None
        ):
            raise ValueError(
                "Trigger 'category spend' requires both trigger_category_id "
                "and trigger_category_spend"
            )
    else:
        if not code:
            raise ValueError("Manual coupons require a coupon code")


# -------------------------
# Admin Schemas
# -------------------------

class CouponCreate(BaseModel):
    # code is optional so the server can auto-generate one (AUTO-XXXXXX)
    # for automatic coupons.
    code: str | None = Field(default=None, min_length=3, max_length=50)
    coupon_type: CouponTypeEnum = CouponTypeEnum.MANUAL
    discount_type: DiscountTypeEnum = DiscountTypeEnum.PERCENTAGE
    value: Decimal = Field(gt=0)
    trigger_type: TriggerTypeEnum = TriggerTypeEnum.NONE
    trigger_min_cart_value: Decimal | None = Field(default=None, gt=0)
    trigger_min_item_count: int | None = Field(default=None, ge=1)
    trigger_category_id: UUID | None = None
    trigger_category_spend: Decimal | None = Field(default=None, gt=0)
    min_order_value: Decimal | None = Field(default=None, gt=0)
    max_uses: int | None = Field(default=None, gt=0)
    max_uses_per_user: int = Field(default=1, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool = Field(default=True)
    internal_only: bool = Field(
        default=False,
        description="Staff/test codes rejected at checkout validation",
    )

    @model_validator(mode="after")
    def _validate_coupon_config(self):
        if self.coupon_type == CouponTypeEnum.MANUAL:
            # Manual coupons never carry triggers — force them off so a stale
            # payload can't create a hybrid record.
            self.trigger_type = TriggerTypeEnum.NONE
            self.trigger_min_cart_value = None
            self.trigger_min_item_count = None
            self.trigger_category_id = None
            self.trigger_category_spend = None

        validate_trigger_config(
            coupon_type=self.coupon_type,
            trigger_type=self.trigger_type,
            code=self.code,
            trigger_min_cart_value=self.trigger_min_cart_value,
            trigger_min_item_count=self.trigger_min_item_count,
            trigger_category_id=self.trigger_category_id,
            trigger_category_spend=self.trigger_category_spend,
        )
        return self


class CouponUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=3, max_length=50)
    coupon_type: CouponTypeEnum | None = None
    discount_type: DiscountTypeEnum | None = None
    value: Decimal | None = Field(default=None, gt=0)
    trigger_type: TriggerTypeEnum | None = None
    trigger_min_cart_value: Decimal | None = Field(default=None, gt=0)
    trigger_min_item_count: int | None = Field(default=None, ge=1)
    trigger_category_id: UUID | None = None
    trigger_category_spend: Decimal | None = Field(default=None, gt=0)
    min_order_value: Decimal | None = Field(default=None, gt=0)
    max_uses: int | None = Field(default=None, gt=0)
    max_uses_per_user: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None
    internal_only: bool | None = None


class CouponRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    code: str
    coupon_type: str
    discount_type: str
    value: Decimal
    trigger_type: str
    trigger_min_cart_value: Decimal | None
    trigger_min_item_count: int | None
    trigger_category_id: UUID | None
    trigger_category_spend: Decimal | None
    min_order_value: Decimal | None
    max_uses: int | None
    max_uses_per_user: int
    times_used: int
    valid_from: datetime
    valid_until: datetime
    is_active: bool
    internal_only: bool = False
    created_by: UUID
    created_at: datetime
    updated_at: datetime


# -------------------------
# Public Schemas
# -------------------------

class CouponValidateRequest(BaseModel):
    code: str


class CouponValidateResponse(BaseModel):
    valid: bool
    message: str
    is_automatic: bool = False
    discount_type: str | None = None
    value: Decimal | None = None
    min_order_value: Decimal | None = None


class ApplyCouponRequest(BaseModel):
    coupon_code: str
