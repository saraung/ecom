from datetime import datetime
from decimal import Decimal
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class PaymentStatusEnum(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProviderEnum(str, Enum):
    DUMMY = "dummy"
    RAZORPAY = "razorpay"
    STRIPE = "stripe"


# -------------------------
# Request Schemas
# -------------------------

class PaymentCreateRequest(BaseModel):
    order_id: UUID
    payment_method: str = Field(default="online")  # kept for compat; Razorpay records the real instrument


class PaymentConfirmRequest(BaseModel):
    payment_intent_id: str
    payment_method_id: str | None = None
    transaction_id: str | None = None  # fast-path: pay_xxx from the checkout callback


# -------------------------
# Response Schemas
# -------------------------

class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    order_id: UUID
    provider: str
    provider_payment_id: str
    transaction_id: str | None
    amount: Decimal
    currency: str
    status: str
    payment_method: str | None
    last_four: str | None
    payment_metadata: dict | None  # 👈 Changed from metadata
    created_at: datetime
    paid_at: datetime | None
    refunded_at: datetime | None


class PaymentIntentResponse(BaseModel):
    client_secret: str
    payment_intent_id: str
    order_id: UUID
    amount: Decimal
    currency: str
    provider: str | None = None
    is_dummy: bool = True