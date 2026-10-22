# app/models/refund.py
"""Refund ledger: every money movement is a row, never a bare status flip.

Lifecycle:
  pending_approval -> (approve) -> executing -> executed | failed
  pending_approval -> (reject)  -> rejected
  <created executed>            -> executed | failed   (within authority)

- ``idempotency_key`` (client UUID per click) makes retries/double-clicks
  safe: one key executes at most once.
- ``approved_by`` is None for within-authority executions; set (to a
  DIFFERENT admin than requested_by and order owner) for approvals.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class RefundStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


class Refund(SQLModel, table=True):
    __tablename__ = "refunds"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    # Nullable additions: all existing cancellation refunds retain their path.
    return_request_id: UUID | None = Field(default=None, foreign_key="return_requests.id", index=True)
    manual_transfer_reference: str | None = Field(default=None, max_length=200)

    amount: Decimal = Field(max_digits=12, decimal_places=2)
    restocking_fee: Decimal = Field(
        default=0, max_digits=12, decimal_places=2
    )

    # Client-generated UUID per refund click — retries reuse the key.
    idempotency_key: str = Field(
        max_length=100, unique=True, index=True
    )

    status: RefundStatus = Field(default=RefundStatus.EXECUTED, index=True)

    # Reason is REQUIRED on the admin path (customer path may omit it).
    reason: str | None = Field(default=None, max_length=500)

    requested_by: UUID | None = Field(
        default=None, foreign_key="users.id"
    )
    approved_by: UUID | None = Field(
        default=None, foreign_key="users.id"
    )

    provider_refund_id: str | None = Field(default=None, index=True)
    provider_status: str | None = None
    error: str | None = None

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    decided_at: datetime | None = None
