"""Delivered-item returns; money movements remain in the existing Refund ledger."""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Enum as SAEnum, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow():
    return datetime.now(timezone.utc)


class ReturnStatus(str, Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURN_SHIPPED = "return_shipped"
    RECEIVED = "received"
    INSPECTION = "inspection"
    REFUND_PENDING = "refund_pending"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class ReturnReason(str, Enum):
    DAMAGED = "damaged"
    WRONG_PRODUCT = "wrong_product"
    DEFECTIVE = "defective"
    MISSING_ACCESSORY = "missing_accessory"
    WRONG_VARIANT = "wrong_variant"
    CHANGED_MIND = "changed_mind"
    OTHER = "other"


REASON_LABELS = {
    "damaged": "Damaged product",
    "wrong_product": "Wrong product received",
    "defective": "Product defective/not working",
    "missing_accessory": "Missing item/accessory",
    "wrong_variant": "Wrong size/variant",
    "changed_mind": "Changed my mind",
    "other": "Other",
}


class ReturnRequest(SQLModel, table=True):
    __tablename__ = "return_requests"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_return_owner_key"),
        CheckConstraint("refund_amount > 0 AND return_fee >= 0", name="ck_return_amounts"),
        CheckConstraint("refund_attempts >= 0", name="ck_return_attempts"),
        CheckConstraint("status IN ('requested','approved','rejected','return_shipped','received','inspection','refund_pending','refunded','cancelled')", name="return_status"),
        CheckConstraint("reason IN ('damaged','wrong_product','defective','missing_accessory','wrong_variant','changed_mind','other')", name="return_reason"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    idempotency_key: str = Field(max_length=64)
    payload_hash: str = Field(max_length=64)
    status: ReturnStatus = Field(default=ReturnStatus.REQUESTED, sa_column=Column(
        SAEnum(ReturnStatus, values_callable=lambda e: [x.value for x in e],
               native_enum=False, create_constraint=False, name="return_status"), nullable=False, index=True))
    reason: ReturnReason = Field(sa_column=Column(
        SAEnum(ReturnReason, values_callable=lambda e: [x.value for x in e],
               native_enum=False, create_constraint=False, name="return_reason"), nullable=False, index=True))
    description: str = Field(default="", max_length=2000)
    decision_note: str | None = Field(default=None, max_length=1000)
    inspection_note: str | None = Field(default=None, max_length=1000)
    inspection_passed: bool | None = None
    refund_amount: Decimal = Field(max_digits=12, decimal_places=2)
    return_fee: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    refund_attempts: int = Field(default=0)
    tracking_number: str | None = Field(default=None, max_length=100, unique=True, index=True)
    tracking_provider: str | None = Field(default=None, max_length=20)
    courier_name: str | None = Field(default=None, max_length=100)
    tracking_status: str | None = Field(default=None, max_length=100)
    shiprocket_order_id: str | None = Field(default=None, max_length=100, unique=True, index=True)
    shiprocket_shipment_id: str | None = Field(default=None, max_length=100, unique=True, index=True)
    shipping_reference: str | None = Field(default=None, max_length=20, unique=True, index=True)
    shipping_requested_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    pickup_requested_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True), index=True)
    updated_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
    approved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    rejected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    shipped_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    received_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    inspected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    refund_requested_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    refunded_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    cancelled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class ReturnItem(SQLModel, table=True):
    __tablename__ = "return_items"
    __table_args__ = (
        UniqueConstraint("return_id", "order_item_id", name="uq_return_item"),
        CheckConstraint("quantity > 0 AND amount >= 0", name="ck_return_item_values"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    return_id: UUID = Field(foreign_key="return_requests.id", index=True)
    order_item_id: UUID = Field(foreign_key="order_items.id", index=True)
    quantity: int
    amount: Decimal = Field(max_digits=12, decimal_places=2)


class ReturnEvidence(SQLModel, table=True):
    __tablename__ = "return_evidence"
    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_return_evidence_size"),)
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    return_id: UUID = Field(foreign_key="return_requests.id", index=True)
    uploaded_by: UUID = Field(foreign_key="users.id")
    storage_key: str = Field(max_length=64, unique=True)
    filename: str = Field(max_length=160)
    size_bytes: int
    sha256: str = Field(max_length=64)
    secure_url: str | None = Field(default=None, max_length=1000)
    cloudinary_public_id: str | None = Field(default=None, max_length=500, index=True)
    cloudinary_type: str | None = Field(default=None, max_length=30)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


class ReturnEvent(SQLModel, table=True):
    __tablename__ = "return_events"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    return_id: UUID = Field(foreign_key="return_requests.id", index=True)
    actor_id: UUID | None = Field(default=None, foreign_key="users.id")
    action: str = Field(max_length=60)
    from_status: str | None = Field(default=None, max_length=20)
    to_status: str = Field(max_length=20)
    note: str | None = Field(default=None, max_length=1000)
    details: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    event_key: str | None = Field(default=None, max_length=180, unique=True)
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True), index=True)
