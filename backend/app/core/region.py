# app/core/region.py
"""Regionalization for a single-currency-per-deployment store.

One switch rules everything: ``PAYMENT_CURRENCY``. This module derives the
display symbol, locale, tax label and country from it (with explicit env
overrides where a deploy needs them), so no rupee signs, GST mentions or
``en-IN`` literals live in business code, emails or prompts.

Frontends must NOT hardcode currency either: the public
``GET /checkout/config`` exposes ``currency``/``locale``/``tax_label``/
``country`` and both web apps format from that response.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.core.config import settings


#: Display symbols. ISO code is always available as a fallback; add a row
#: here (not a literal elsewhere) when onboarding a new currency.
CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "JPY": "¥",
    "AED": "د.إ",
    "CAD": "$",
    "AUD": "$",
}

#: Stripe/Razorpay zero-decimal currencies (no ×100 minor units).
#: Subset of Stripe's list covering realistic near-term deploys.
ZERO_DECIMAL_CURRENCIES = frozenset({"JPY", "KRW", "VND", "CLP", "COP"})


def currency_code() -> str:
    """Active ISO currency (INR/EUR/USD…), uppercased, never empty."""
    return (settings.PAYMENT_CURRENCY or "INR").upper()


def currency_symbol(code: str | None = None) -> str:
    """Display symbol for a code (defaults to the active one)."""
    code = (code or currency_code()).upper()
    return CURRENCY_SYMBOLS.get(code, code + " ")


def display_locale() -> str:
    """BCP-47 locale for number/date grouping (explicit env wins)."""
    if settings.DISPLAY_LOCALE:
        return settings.DISPLAY_LOCALE
    return "en-IN" if currency_code() == "INR" else "en-US"


def tax_label() -> str:
    """Customer-facing tax name: GST for India, VAT elsewhere.

    Explicit TAX_LABEL env always wins (e.g. "Sales Tax" for a US store).
    """
    if settings.TAX_LABEL:
        return settings.TAX_LABEL
    return "GST" if currency_code() == "INR" else "VAT"


def default_country() -> str:
    """Store's home country for address defaults and fallbacks."""
    return settings.DEFAULT_COUNTRY or "India"


def format_money(amount) -> str:
    """Human string for emails/messages/receipts, e.g. ₹1,234.50 / €1,234.50.

    Same shape as the old hardcoded ``f"₹{amount:,.2f}"`` so existing
    message asserts keep passing under INR; other currencies swap the
    symbol. Amounts are quantised, never silently truncated.
    """
    value = Decimal(str(amount or 0)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{currency_symbol()}{value:,.2f}"


def minor_units(amount, *, currency: str | None = None) -> int:
    """Provider minor units for a full-unit amount (paise/cents, or whole
    units for zero-decimal currencies like JPY — where ×100 would overcharge
    100×). Both Stripe and Razorpay share this rule."""
    value = Decimal(str(amount or 0))
    if (currency or currency_code()).upper() in ZERO_DECIMAL_CURRENCIES:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor_units(value, *, currency: str | None = None) -> Decimal:
    """Full-unit amount from a provider minor-unit integer. Inverse of
    minor_units() — read paths (refunds/charges) must use this instead of
    a bare ``/ 100``, which under-reports 100× for zero-decimal currencies."""
    if (currency or currency_code()).upper() in ZERO_DECIMAL_CURRENCIES:
        return Decimal(str(value or 0))
    return Decimal(str(value or 0)) / 100


def provider_compat_error(provider: str) -> str | None:
    """Boot-time incompatibility between gateway and currency, if any.

    Razorpay settles INR (UPI/netbanking rails); a non-INR deployment on
    Razorpay will fail at the provider, so refuse to boot quietly into it.
    Stripe is currency-generic — allowed with anything (INR included,
    though UPI coverage makes Razorpay the better business choice there).
    """
    name = (provider or "").strip().lower()
    if name == "razorpay" and currency_code() != "INR":
        return (
            f"PAYMENT_PROVIDER=razorpay with PAYMENT_CURRENCY={currency_code()} — "
            "Razorpay settles INR rails; use PAYMENT_PROVIDER=stripe for "
            "non-INR deployments"
        )
    return None
