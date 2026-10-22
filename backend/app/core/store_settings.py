# app/core/store_settings.py
"""Fresh DB policy for financial operations; TTL cache for sessionless display.

Environment values bootstrap a missing row. They never replace an existing
policy on a financial DB failure. Callers pass one immutable snapshot through
each pricing/refund operation; session reads do not publish uncommitted policy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.config import STORE_DEFAULTS, settings

#: Upper bound on cross-worker staleness after an admin save: the saving
#: worker refreshes synchronously (see refresh_store_settings), every other
#: worker picks the new row up at most TTL_SECONDS later. Kept small (10s)
#: because these are money values — checkout pricing briefly disagreeing
#: across workers is a correctness issue, not just a display lag. Hot paths
#: still never touch SQL: they read the cached snapshot.
TTL_SECONDS = 10.0

_CACHE: dict = {"snapshot": None, "expires_at": 0.0}


@dataclass(frozen=True)
class StoreSettingsSnapshot:
    """Plain (detached-safe) copy of the policy row.

    ``source`` is "database" once an admin has saved (or the env seed ran),
    "environment" when the table is missing/unreachable.
    """

    # Scales: tax_rate is a fraction (0.18); restocking fees are percents
    # (5.0) — matching the refund engine (divides by 100) and the admin UI
    # (converts tax only). Keep them in sync.
    tax_rate: float = STORE_DEFAULTS["tax_rate"]
    free_shipping_threshold: float = STORE_DEFAULTS["free_shipping_threshold"]
    shipping_cost: float = STORE_DEFAULTS["shipping_cost"]
    cod_fee: float = STORE_DEFAULTS["cod_fee"]
    cod_min_order_value: float = STORE_DEFAULTS["cod_min_order_value"]
    cod_max_order_value: float = STORE_DEFAULTS["cod_max_order_value"]
    restocking_fee_pending: float = STORE_DEFAULTS["restocking_fee_pending"]
    restocking_fee_confirmed: float = STORE_DEFAULTS["restocking_fee_confirmed"]
    restocking_fee_processing: float = STORE_DEFAULTS["restocking_fee_processing"]
    refund_processing_days: int = STORE_DEFAULTS["refund_processing_days"]
    pending_order_expiry_minutes: int = STORE_DEFAULTS["pending_order_expiry_minutes"]
    source: str = "environment"


def _snapshot_from_env() -> StoreSettingsSnapshot:
    return StoreSettingsSnapshot(
        tax_rate=float(settings.TAX_RATE),
        free_shipping_threshold=float(settings.FREE_SHIPPING_THRESHOLD),
        shipping_cost=float(settings.SHIPPING_COST),
        cod_fee=float(settings.COD_FEE),
        cod_min_order_value=float(settings.COD_MIN_ORDER_VALUE),
        cod_max_order_value=float(settings.COD_MAX_ORDER_VALUE),
        restocking_fee_pending=float(settings.RESTOCKING_FEE_PENDING),
        restocking_fee_confirmed=float(settings.RESTOCKING_FEE_CONFIRMED),
        restocking_fee_processing=float(settings.RESTOCKING_FEE_PROCESSING),
        refund_processing_days=int(settings.REFUND_PROCESSING_DAYS),
        pending_order_expiry_minutes=int(settings.PENDING_ORDER_EXPIRY_MINUTES),
        source="environment",
    )


def _snapshot_from_row(row) -> StoreSettingsSnapshot:
    return StoreSettingsSnapshot(
        tax_rate=float(row.tax_rate),
        free_shipping_threshold=float(row.free_shipping_threshold),
        shipping_cost=float(row.shipping_cost),
        cod_fee=float(row.cod_fee),
        cod_min_order_value=float(row.cod_min_order_value),
        cod_max_order_value=float(row.cod_max_order_value),
        restocking_fee_pending=float(row.restocking_fee_pending),
        restocking_fee_confirmed=float(row.restocking_fee_confirmed),
        restocking_fee_processing=float(row.restocking_fee_processing),
        refund_processing_days=int(row.refund_processing_days),
        pending_order_expiry_minutes=int(row.pending_order_expiry_minutes),
        source="database",
    )


def _cached() -> StoreSettingsSnapshot | None:
    if time.monotonic() < _CACHE["expires_at"]:
        return _CACHE["snapshot"]
    return None


def _store(snapshot: StoreSettingsSnapshot) -> StoreSettingsSnapshot:
    _CACHE["snapshot"] = snapshot
    _CACHE["expires_at"] = time.monotonic() + TTL_SECONDS
    return snapshot


def invalidate_cache() -> None:
    """Force the next read to hit the database (or env)."""
    _CACHE["snapshot"] = None
    _CACHE["expires_at"] = 0.0


def read_store_settings(session):
    """Return the singleton row or None. Pure read — never writes.

    Request handlers that must not cause side effects (notably GET) use
    this; callers fall back to the env snapshot when no row exists yet.
    """
    from app.models.store_settings import StoreSettings

    with session.no_autoflush:
        return session.get(StoreSettings, 1, populate_existing=True)


def ensure_store_settings(session, *, commit: bool = True):
    """Return the singleton row, seeding it from env on first use.

    Commits the seed so concurrent workers converge on one row. Only
    called from startup seeding and write paths — never from reads.
    """
    from app.models.store_settings import StoreSettings

    row = session.get(StoreSettings, 1)
    if row is None:
        env = _snapshot_from_env()
        row = StoreSettings(
            id=1,
            tax_rate=env.tax_rate,
            free_shipping_threshold=env.free_shipping_threshold,
            shipping_cost=env.shipping_cost,
            cod_fee=env.cod_fee,
            cod_min_order_value=env.cod_min_order_value,
            cod_max_order_value=env.cod_max_order_value,
            restocking_fee_pending=env.restocking_fee_pending,
            restocking_fee_confirmed=env.restocking_fee_confirmed,
            restocking_fee_processing=env.restocking_fee_processing,
            refund_processing_days=env.refund_processing_days,
            pending_order_expiry_minutes=env.pending_order_expiry_minutes,
        )
        session.add(row)
        if commit:
            session.commit()
            session.refresh(row)
        else:
            session.flush()
    return row


def seed_store_settings(session) -> None:
    """Idempotent startup seed: guarantee the row exists before serving.

    Safe to call on every boot (and concurrently from several workers —
    the PK converges them on one row). A failed seed never crashes boot:
    request paths degrade to the env snapshot via get_store_settings.
    """
    try:
        ensure_store_settings(session)
    except Exception as exc:
        session.rollback()
        print(f"⚠️ store_settings seed skipped ({type(exc).__name__}: {exc})")


def refresh_store_settings(session) -> StoreSettingsSnapshot:
    """Re-read the row and recache. Called after every admin save."""
    invalidate_cache()
    return _store(_snapshot_from_row(ensure_store_settings(session)))


def get_store_settings(session=None, *, seed: bool = True) -> StoreSettingsSnapshot:
    """Session reads are authoritative; sessionless reads are cached display."""
    if session is not None:
        from fastapi import HTTPException
        try:
            row = read_store_settings(session)
            if row is None and seed:
                row = ensure_store_settings(session)
            return _snapshot_from_row(row) if row is not None else _snapshot_from_env()
        except Exception as exc:
            # The caller owns rollback. In particular, do not commit a cart or
            # refund just because configuration could not be read.
            raise HTTPException(503, "Store policy is temporarily unavailable") from exc
    hit = _cached()
    if hit is not None:
        return hit
    try:
        from sqlmodel import Session
        from app.db.database import engine
        with Session(engine) as display_session:
            row = read_store_settings(display_session)
            snapshot = _snapshot_from_row(row) if row is not None else _snapshot_from_env()
        return _store(snapshot)
    except Exception:
        # Display-only degraded reads retain the last known DB policy rather
        # than replacing it with different prices from the environment.
        return _store(_CACHE["snapshot"] or _snapshot_from_env())


def update_store_settings(session, data: dict, actor_id=None, *, commit: bool = True):
    """Apply an admin save (validated upstream), recache, return the row."""
    from app.models.store_settings import StoreSettings

    row = ensure_store_settings(session, commit=commit)
    for key, value in data.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    from datetime import datetime, timezone

    row.updated_by = actor_id
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
        refresh_store_settings(session)
    else:
        session.flush()
    return row


#: Audit actions that count as settings history. Restores are undoable too,
#: so restoring a restore always offers a way back.
RESTOREABLE_ACTIONS = frozenset({"settings.store_updated", "settings.store_restored"})


def restore_values(session, audit_id):
    """Return the (key → value) dict that undoes one past settings save.

    Only keys changed by that save are included, restricted to known
    setting keys. Raises ValueError when the entry is missing, is not a
    settings change, or carries nothing restorable. Callers validate
    ranges (via the update schema) and write their own audit entry.
    """
    from uuid import UUID as _UUID

    from app.models.admin_audit import AdminAuditLog

    try:
        wanted = _UUID(str(audit_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Not a settings change entry")
    entry = session.get(AdminAuditLog, wanted)
    if (
        entry is None
        or entry.entity != "settings"
        or entry.action not in RESTOREABLE_ACTIONS
    ):
        raise ValueError("Not a settings change entry")
    values = {
        k: v for k, v in (entry.before or {}).items() if k in STORE_DEFAULTS
    }
    if not values:
        raise ValueError("Nothing to restore from this entry")
    return values, entry
