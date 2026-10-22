from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.product_return import ReturnReason


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReturnItemInput(StrictInput):
    order_item_id: UUID
    quantity: int = Field(gt=0, le=100000, strict=True)


class ReturnCreate(StrictInput):
    idempotency_key: UUID
    reason: ReturnReason
    description: str = Field(default="", max_length=2000)
    items: list[ReturnItemInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_items_and_reason(self):
        if len({item.order_item_id for item in self.items}) != len(self.items):
            raise ValueError("Select each purchased item only once")
        if self.reason == ReturnReason.OTHER and len(self.description) < 10:
            raise ValueError("Please explain the Other reason (at least 10 characters)")
        return self


class ReturnDecision(StrictInput):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def rejection_note(self):
        if self.decision == "reject" and not self.note:
            raise ValueError("A rejection note is required")
        return self


class ReturnNote(StrictInput):
    note: str = Field(default="", max_length=1000)


class ReturnInspection(StrictInput):
    passed: bool = Field(strict=True)
    note: str = Field(min_length=1, max_length=1000)


class ReturnTracking(StrictInput):
    tracking_number: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    courier_name: str = Field(min_length=1, max_length=100)
    provider: Literal["manual", "shiprocket"] = "manual"


class ReturnRefundInput(StrictInput):
    # COD only: an attestation of repayment, never a request to a PSP.
    manual_transfer_reference: str | None = Field(default=None, min_length=3, max_length=200)
