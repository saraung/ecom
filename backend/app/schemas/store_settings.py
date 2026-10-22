# app/schemas/store_settings.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StoreSettingsRestoreRequest(BaseModel):
    """Undo one past save identified by its audit entry id."""

    audit_id: UUID


class StoreSettingsHistoryChange(BaseModel):
    key: str
    before: float | int | None = None
    after: float | None = None


class StoreSettingsHistoryEntry(BaseModel):
    audit_id: UUID
    action: str
    actor_email: str | None = None
    created_at: datetime | None = None
    changes: list[StoreSettingsHistoryChange] = []


class StoreSettingsHistoryResponse(BaseModel):
    entries: list[StoreSettingsHistoryEntry] = []


class StoreSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tax_rate: float
    free_shipping_threshold: float
    shipping_cost: float
    cod_fee: float
    cod_min_order_value: float
    cod_max_order_value: float
    restocking_fee_pending: float
    restocking_fee_confirmed: float
    restocking_fee_processing: float
    refund_processing_days: int
    pending_order_expiry_minutes: int
    # "database" once saved (or env-seeded), "environment" on pure fallback.
    source: str = "environment"
    updated_at: datetime | None = None
    updated_by: UUID | None = None
    # Regionalization mirrors the public checkout config so the admin UI
    # formats money/labels from live values instead of hardcoded symbols.
    currency: str = "INR"
    tax_label: str = "GST"


class StoreSettingsUpdate(BaseModel):
    # tax_rate is a FRACTION (0.18 = 18%); restocking fees are PERCENTS
    # (5.0 = 5%) — see the model. Ranges below enforce each scale.
    tax_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    free_shipping_threshold: float | None = Field(default=None, ge=0.0)
    shipping_cost: float | None = Field(default=None, ge=0.0)
    cod_fee: float | None = Field(default=None, ge=0.0)
    cod_min_order_value: float | None = Field(default=None, ge=0.0)
    cod_max_order_value: float | None = Field(default=None, ge=0.0)
    restocking_fee_pending: float | None = Field(default=None, ge=0.0, le=100.0)
    restocking_fee_confirmed: float | None = Field(default=None, ge=0.0, le=100.0)
    restocking_fee_processing: float | None = Field(default=None, ge=0.0, le=100.0)
    refund_processing_days: int | None = Field(default=None, ge=1, le=30)
    pending_order_expiry_minutes: int | None = Field(default=None, ge=5, le=1440)
