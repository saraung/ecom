# app/schemas/refund.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class RefundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    return_request_id: UUID | None = None
    manual_transfer_reference: str | None = None
    order_number: str | None = None
    amount: Decimal
    restocking_fee: Decimal = Decimal(0)
    status: str
    reason: str | None = None
    requested_by: UUID | None = None
    requester_email: str | None = None
    approved_by: UUID | None = None
    provider_refund_id: str | None = None
    provider_status: str | None = None
    error: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class RefundListResponse(BaseModel):
    refunds: list[RefundRead]
    total: int
    page: int
    limit: int
    total_pages: int


class AdminCancelRequest(BaseModel):
    """Unified admin cancel: status + optional money movement in one action.

    refund_choice:
      - "later" (default): cancel + restock, money stays, refundable balance
        left open for a later explicit refund (tracked for follow-up).
      - "now": cancel + restock + execute refund via the pipeline (within
        authority) or stage a pending approval (above limit / self-order).
    """

    reason: str
    refund_choice: str = "later"
    restock: bool = True
    notify_customer: bool = True
    # Client-generated UUID per dialog open — retries reuse the key.
    idempotency_key: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("A cancellation reason is required")
        if len(v) > 500:
            raise ValueError("Reason must be at most 500 characters")
        return v.strip()

    @field_validator("refund_choice")
    @classmethod
    def choice_valid(cls, v: str) -> str:
        if v not in ("now", "later"):
            raise ValueError("refund_choice must be 'now' or 'later'")
        return v


class AdminRefundRequest(BaseModel):
    """Refund an ALREADY-cancelled order (the "refund later" follow-up).

    Cancelling with ``refund_choice="later"`` deliberately moves no money, so
    the captured balance needs a second, explicit step. This is that step.
    """

    reason: str
    #: None refunds the full outstanding balance (grand_total - restocking
    #: fee - anything already refunded). A value caps it (partial refund).
    amount: Decimal | None = None
    notify_customer: bool = True
    #: Client-generated UUID per dialog open — retries reuse the key.
    idempotency_key: str | None = None

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("A refund reason is required")
        if len(v) > 500:
            raise ValueError("Reason must be at most 500 characters")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("amount must be greater than zero")
        return v


class RefundRejectRequest(BaseModel):
    note: str | None = None


class RefundDecisionResponse(BaseModel):
    processed: bool
    requires_approval: bool = False
    amount: Decimal | None = None
    refund_row_id: str | None = None
    refund_id: str | None = None
    message: str
