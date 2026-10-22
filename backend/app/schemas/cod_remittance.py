from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CodInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CodRemittanceItemInput(CodInput):
    awb: str | None = Field(default=None, max_length=120)
    order_number: str | None = Field(default=None, max_length=120)
    cod_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    deductions: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    net_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    remitted_amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def needs_reference(self):
        if not self.awb and not self.order_number:
            raise ValueError("Each COD line needs an AWB or an order number")
        return self


class ManualBatchCreate(CodInput):
    crf_id: str = Field(min_length=1, max_length=120)
    remittance_date: date
    notes: str | None = Field(default=None, max_length=4000)
    items: list[CodRemittanceItemInput] = Field(min_length=1, max_length=500)


class ConfirmReceiptRequest(CodInput):
    utr: str = Field(min_length=1, max_length=120)
    bank_credit_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    bank_credit_date: date
    bank_account_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    accept_difference: bool = False
    difference_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def difference_needs_reason(self):
        if self.accept_difference and not (self.difference_reason or "").strip():
            raise ValueError("A reason is required when accepting a bank difference")
        return self


class ResolveItemRequest(CodInput):
    item_id: UUID
    action: Literal["accept_match", "exclude"]
    note: str | None = Field(default=None, max_length=500)


class BulkCollectRequest(CodInput):
    order_ids: list[UUID] = Field(min_length=1, max_length=100)
