"""Shared envelope helpers for MCP tools (imported by tool modules).

Only ever holds import-light helpers: app.core.region (settings) is safe
to import from every tool module without cycles.
"""
from app.core.region import currency_code, currency_symbol


def money_envelope() -> dict:
    """Currency keys for money-bearing tool responses (envelope-level).

    Reads the live deployment currency (PAYMENT_CURRENCY) per call, so an
    env switch propagates without prompt or tool edits. Merge at the top
    level of success responses only — never inside row dicts (row
    whitelists stay stable). Counts and quantities are not money and get
    no currency.
    """
    return {"currency": currency_code(), "currency_symbol": currency_symbol()}
