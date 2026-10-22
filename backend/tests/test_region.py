"""
Tests for single-currency-per-deployment regionalization (app/core/region.py).

Covers:
  1. INR defaults: code/symbol/locale/tax label/format shape.
  2. Derivation under EUR (symbol, locale, VAT label).
  3. TAX_LABEL explicit override wins over derivation.
  4. Minor-unit round-trips (2-decimal and zero-decimal JPY).
  5. Provider/currency compatibility gate.
  6. Checkout config exposes the region block for frontends.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_region.py -q
"""
from decimal import Decimal

import pytest

import app.models  # noqa: F401  (complete SQLModel metadata)
from app.core import region
from app.core.config import settings


def test_1_inr_defaults():
    assert region.currency_code() == "INR"
    assert region.currency_symbol() == "₹"
    assert region.display_locale() == "en-IN"
    assert region.tax_label() == "GST"
    assert region.default_country() == "India"
    assert region.format_money(1500) == "₹1,500.00"
    assert region.format_money(None) == "₹0.00"


def test_2_derivation_under_eur(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_CURRENCY", "EUR")
    assert region.currency_code() == "EUR"
    assert region.currency_symbol() == "€"
    assert region.display_locale() == "en-US"
    assert region.tax_label() == "VAT"
    assert region.format_money(1234.5) == "€1,234.50"


def test_3_tax_label_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "PAYMENT_CURRENCY", "USD")
    monkeypatch.setattr(settings, "TAX_LABEL", "Sales Tax")
    assert region.tax_label() == "Sales Tax"
    monkeypatch.setattr(settings, "DISPLAY_LOCALE", "de-DE")
    assert region.display_locale() == "de-DE"


def test_4_minor_unit_round_trips(monkeypatch):
    assert region.minor_units(Decimal("1500.00")) == 150000
    assert region.from_minor_units(150000) == Decimal("1500")
    monkeypatch.setattr(settings, "PAYMENT_CURRENCY", "JPY")
    assert region.minor_units(500) == 500
    assert region.from_minor_units(500) == Decimal("500")
    # ...instead of the ×100 overcharge a naive conversion would produce.
    assert region.minor_units(500) != 50000


def test_5_provider_compat_gate(monkeypatch):
    assert region.provider_compat_error("razorpay") is None
    assert region.provider_compat_error("stripe") is None
    assert region.provider_compat_error("dummy") is None
    monkeypatch.setattr(settings, "PAYMENT_CURRENCY", "EUR")
    assert region.provider_compat_error("stripe") is None
    err = region.provider_compat_error("razorpay")
    assert err is not None and "stripe" in err.lower()


def test_6_checkout_config_carries_region_block():
    from app.api.v1.checkout import get_checkout_config

    # Session-less read: seeded/fallback snapshot is enough for the block.
    cfg = get_checkout_config()
    assert cfg.currency == region.currency_code()
    assert cfg.locale == region.display_locale()
    assert cfg.tax_label == region.tax_label()
    assert cfg.country == region.default_country()
    # Existing money hints still present (additive change).
    assert cfg.tax_rate >= 0
