# app/models/store_settings.py
"""Single-row store policy table (tax, shipping, COD, refunds, expiry).

These knobs used to live only in env vars, so every price tweak needed a
deploy. The row is seeded from the env on first read; the admin Store
settings page edits it afterwards. Hot paths read through the cached
snapshot in ``app.core.store_settings`` (60s TTL) — never per-request SQL.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Field, SQLModel

from app.core.config import STORE_DEFAULTS


class StoreSettings(SQLModel, table=True):
    __tablename__ = "store_settings"

    # Singleton row — id is always 1.
    id: int = Field(default=1, primary_key=True)

    # Python-side defaults only (no server DDL default): the seeder writes
    # explicit values anyway. All mirror STORE_DEFAULTS — do not edit here.
    # Tax & pricing (FRACTION scale: 0.18 = 18% — pricing multiplies directly)
    tax_rate: float = Field(default=STORE_DEFAULTS["tax_rate"])

    # Shipping
    free_shipping_threshold: float = Field(default=STORE_DEFAULTS["free_shipping_threshold"])
    shipping_cost: float = Field(default=STORE_DEFAULTS["shipping_cost"])

    # COD
    cod_fee: float = Field(default=STORE_DEFAULTS["cod_fee"])
    cod_min_order_value: float = Field(default=STORE_DEFAULTS["cod_min_order_value"])
    cod_max_order_value: float = Field(default=STORE_DEFAULTS["cod_max_order_value"])

    # Cancellations & refunds. Restocking fees are PERCENT scale (5.0 = 5% —
    # the refund engine divides by 100 itself, and fee_percentage is shown
    # to customers with a % suffix). Do NOT store fractions here: 0.05
    # would charge five-hundredths of a percent. Customer-facing days below.
    restocking_fee_pending: float = Field(default=STORE_DEFAULTS["restocking_fee_pending"])
    restocking_fee_confirmed: float = Field(default=STORE_DEFAULTS["restocking_fee_confirmed"])
    restocking_fee_processing: float = Field(default=STORE_DEFAULTS["restocking_fee_processing"])
    refund_processing_days: int = Field(default=STORE_DEFAULTS["refund_processing_days"])

    # Abandoned unpaid online orders (auto-cancel sweep)
    pending_order_expiry_minutes: int = Field(default=STORE_DEFAULTS["pending_order_expiry_minutes"])

    updated_by: UUID | None = Field(default=None, foreign_key="users.id")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
