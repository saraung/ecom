from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict, field_validator


class PaymentMethodEnum(str, Enum):
    """
    Checkout-level payment choice — only two options exist:

      - COD:    Cash on Delivery, no gateway involved
      - ONLINE: Pay now via Razorpay. The customer picks the actual
        instrument (card / UPI / netbanking / wallet) inside Razorpay's
        checkout modal, so the backend doesn't model it here.
    """
    COD = "cod"        # Cash on Delivery
    ONLINE = "online"  # Razorpay — instrument chosen in the modal


class CheckoutRequest(BaseModel):
    shipping_address_id: UUID
    billing_address_id: UUID | None = None  # If not provided, use shipping address
    payment_method: PaymentMethodEnum = Field(default=PaymentMethodEnum.ONLINE)

    @field_validator("payment_method", mode="before")
    @classmethod
    def _coerce_legacy_instrument_names(cls, v):
        """Backward compatibility: old clients that send Razorpay instrument
        names (card / upi / netbanking / ...) at checkout are all just ONLINE —
        Razorpay's modal handles the instrument choice."""
        if isinstance(v, str) and v.strip().lower() in {"card", "upi", "netbanking", "wallet", "emi"}:
            return PaymentMethodEnum.ONLINE.value
        return v


class CheckoutConfigResponse(BaseModel):
    """Client-facing checkout pricing configuration.

    Display-only hints for the storefront (COD fee, COD eligibility limits,
    shipping/tax rules) so the UI never hardcodes business rules. The server
    recomputes everything when the order is actually placed (POST /checkout),
    so a stale or tampered client copy can never change what is charged.
    """

    cod_fee: float
    cod_min_order_value: float
    cod_max_order_value: float
    free_shipping_threshold: float
    shipping_cost: float
    tax_rate: float
    # Regionalization: the storefront formats ALL money/labels from these —
    # never hardcoded symbols. Single currency per deployment.
    currency: str = "INR"
    locale: str = "en-IN"
    tax_label: str = "GST"
    country: str = "India"
    support_phone: str = ""


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_number: str
    user_id: UUID
    
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    shipping_total: Decimal
    cod_fee: Decimal = Decimal("0.00")
    grand_total: Decimal
    
    status: str
    payment_status: str
    payment_method: str | None = None
    
    placed_at: datetime
    shipped_at: datetime | None
    delivered_at: datetime | None


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_name: str
    variant_sku: str
    variant_attributes: dict
    quantity: int
    unit_price: Decimal
    line_total: Decimal