"""COD remittance batches received from Shiprocket or entered manually.

This module is intentionally separate from :mod:`app.models.payment`:

* ``Payment(provider=cod)`` records the courier collecting cash from the
  customer at delivery.
* A remittance records Shiprocket paying the merchant for those collected
  orders.

Creating a second Payment row for a remittance would double-count revenue, so
remittances live here and only update denormalized COD totals on ``Order``.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, JSON, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CodRemittanceStatus(str, Enum):
    PENDING = "pending"
    RECONCILED = "reconciled"
    DISCREPANCY = "discrepancy"
    VOID = "void"


class CodRemittanceSource(str, Enum):
    CSV = "csv"
    MANUAL = "manual"
    SIMULATOR = "simulator"


class CodRemittanceItemStatus(str, Enum):
    MATCHED = "matched"
    AMOUNT_MISMATCH = "amount_mismatch"
    ORDER_NOT_FOUND = "order_not_found"
    NOT_COD = "not_cod"
    NOT_DELIVERED = "not_delivered"
    CASH_NOT_COLLECTED = "cash_not_collected"
    ALREADY_REMITTED = "already_remitted"
    DUPLICATE = "duplicate"
    ADJUSTMENT = "adjustment"


class CodRemittance(SQLModel, table=True):
    __tablename__ = "cod_remittances"
    #: Case-insensitive uniqueness only while the batch is active. Voiding a
    #: batch frees its CRF reference for a corrected re-import; the voided row
    #: stays in the audit trail with the original spelling.
    __table_args__ = (
        Index(
            "uq_cod_remittances_crf_active",
            "crf_key",
            unique=True,
            postgresql_where=text("status <> 'void'"),
            sqlite_where=text("status <> 'void'"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    #: Shiprocket panel's CRF (COD Remittance File) id, or a manual batch ref.
    crf_id: str = Field(max_length=120, index=True)
    #: Normalized ``crf_id`` used by the active-only partial unique index.
    crf_key: str = Field(max_length=120, index=True)
    provider: str = Field(default="shiprocket", max_length=40)
    remittance_date: date = Field(default_factory=date.today)
    status: str = Field(default=CodRemittanceStatus.PENDING.value, max_length=20, index=True)

    gross_cod: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    deductions_total: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    net_expected: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)

    bank_credit_amount: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)
    utr: str | None = Field(default=None, max_length=120, index=True)
    bank_credit_date: date | None = None
    bank_account_ref: str | None = Field(default=None, max_length=120)
    difference: Decimal | None = Field(default=None, max_digits=12, decimal_places=2)

    source: str = Field(default=CodRemittanceSource.MANUAL.value, max_length=20)
    source_filename: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    raw_meta: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    imported_by: UUID | None = Field(default=None, foreign_key="users.id")
    reconciled_by: UUID | None = Field(default=None, foreign_key="users.id")
    reconciled_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True), index=True)
    updated_at: datetime = Field(
        default_factory=utcnow,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": utcnow},
    )


class CodRemittanceItem(SQLModel, table=True):
    __tablename__ = "cod_remittance_items"
    __table_args__ = (
        UniqueConstraint("remittance_id", "line_hash", name="uq_cod_remittance_line"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    remittance_id: UUID = Field(
        foreign_key="cod_remittances.id", ondelete="CASCADE", index=True
    )
    order_id: UUID | None = Field(
        default=None, foreign_key="orders.id", ondelete="SET NULL", index=True
    )

    awb: str | None = Field(default=None, max_length=120, index=True)
    order_ref: str | None = Field(default=None, max_length=120)
    cod_amount: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    deductions: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    net_amount: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)
    remitted_amount: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=2)

    match_status: str = Field(default=CodRemittanceItemStatus.MATCHED.value, max_length=30, index=True)
    match_note: str | None = Field(default=None, max_length=500)
    line_hash: str = Field(max_length=64)
    raw_row: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
