"""
Tests for DB-backed store settings (Phase C + seed/rollback hardening).

Covers:
  0. Read path is side-effect-free (no row created on reads).
  1. First read seeds the singleton row from env (source "database").
  2. Session-less reads work (cache, then env fallback) — the pricing
     helpers and model properties rely on this.
  3. Admin updates take effect immediately (cache invalidated).
  4. Update schema rejects out-of-range values.
  5. Partial updates keep untouched fields.
  6. All four default sources agree (STORE_DEFAULTS, config, model, snapshot).
  7. Cross-worker visibility is bounded by a small TTL.
  8. restore_values() round-trips one save and rejects bad entries.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_store_settings.py -q
"""
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel, Session, create_engine, select

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.core import store_settings as ss
from app.core.config import STORE_DEFAULTS
from app.core.config import settings as env_settings
from app.models.admin_audit import AdminAuditLog
from app.models.store_settings import StoreSettings
from app.schemas.store_settings import StoreSettingsUpdate


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    ss.invalidate_cache()
    with Session(engine) as s:
        yield s
    ss.invalidate_cache()


def test_0_read_path_creates_no_row():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    ss.invalidate_cache()
    try:
        with Session(engine) as s:
            assert ss.read_store_settings(s) is None
            assert s.exec(select(StoreSettings)).all() == []
    finally:
        ss.invalidate_cache()


def test_6_default_sources_agree(session):
    model_defaults = {k: getattr(StoreSettings(id=1), k) for k in STORE_DEFAULTS}
    assert model_defaults == STORE_DEFAULTS
    snap_defaults = {
        k: getattr(ss.StoreSettingsSnapshot(), k) for k in STORE_DEFAULTS
    }
    assert snap_defaults == STORE_DEFAULTS
    for key in STORE_DEFAULTS:
        assert float(getattr(env_settings, key.upper())) == float(STORE_DEFAULTS[key])


def test_7_cross_worker_visibility_bounded_by_ttl(session):
    # Money values must converge across workers quickly after a save.
    assert ss.TTL_SECONDS <= 10
    ss.get_store_settings(session)  # warm the cache
    # Simulate another worker writing directly (bypassing the recache).
    row = session.get(StoreSettings, 1)
    row.tax_rate = 0.25
    session.add(row)
    session.commit()
    ss.invalidate_cache()  # TTL-expiry equivalent
    assert ss.get_store_settings(session).tax_rate == 0.25


def _audit(session, action, entity, before, after):
    entry = AdminAuditLog(action=action, entity=entity, before=before, after=after)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def test_8_restore_values_round_trip(session):
    ss.get_store_settings(session)
    entry = _audit(
        session,
        "settings.store_updated",
        "settings",
        {"tax_rate": 0.18, "shipping_cost": 50.0},
        {"tax_rate": 0.28, "shipping_cost": 99.0},
    )
    values, found = ss.restore_values(session, entry.id)
    assert values == {"tax_rate": 0.18, "shipping_cost": 50.0}
    assert found.id == entry.id
    # Applying the values really reverts the row.
    ss.update_store_settings(session, values, actor_id=None)
    snap = ss.get_store_settings(session)
    assert snap.tax_rate == 0.18
    assert snap.shipping_cost == 50.0


def test_9_restore_values_rejects(session):
    ss.get_store_settings(session)
    other = _audit(session, "refund.approved", "refund", {"x": 1}, {"x": 2})
    with pytest.raises(ValueError):
        ss.restore_values(session, other.id)
    empty = _audit(session, "settings.store_updated", "settings", {}, {})
    with pytest.raises(ValueError):
        ss.restore_values(session, empty.id)
    unknown = _audit(
        session, "settings.store_updated", "settings", {"nope": 1}, {"nope": 2}
    )
    with pytest.raises(ValueError):
        ss.restore_values(session, unknown.id)
    with pytest.raises(ValueError):
        ss.restore_values(session, uuid4())
    with pytest.raises(ValueError):
        ss.restore_values(session, "not-a-uuid")


# --- Endpoint-level wiring (functions called directly with stub auth;
# repo conventions test services against sqlite, not HTTP). ---

from types import SimpleNamespace  # noqa: E402

from fastapi import HTTPException  # noqa: E402

from app.api.v1.admin import settings as settings_api  # noqa: E402
from app.schemas.store_settings import (  # noqa: E402
    StoreSettingsRestoreRequest,
    StoreSettingsUpdate,
)

_STUB_USER = SimpleNamespace(id=None)


def test_10_get_endpoint_is_read_only():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    ss.invalidate_cache()
    try:
        with Session(engine) as s:
            read = settings_api.get_store_policy(s, _STUB_USER)
            assert read.source == "environment"
            assert read.tax_rate == float(env_settings.TAX_RATE)
            assert s.exec(select(StoreSettings)).all() == []
    finally:
        ss.invalidate_cache()


def test_11_restore_endpoint_round_trip_with_audit(session):
    import time

    ss.get_store_settings(session)
    first = _audit(
        session,
        "settings.store_updated",
        "settings",
        {"tax_rate": 0.18},
        {"tax_rate": 0.28},
    )
    time.sleep(0.02)
    second = _audit(
        session,
        "settings.store_updated",
        "settings",
        {"shipping_cost": 50.0},
        {"shipping_cost": 99.0},
    )

    hist = settings_api.get_store_history(session, _STUB_USER, limit=5)
    assert [e.audit_id for e in hist.entries] == [second.id, first.id]
    assert [c.model_dump() for c in hist.entries[0].changes] == [
        {"key": "shipping_cost", "before": 50.0, "after": 99.0}
    ]

    # Current row holds the "new" values; restore the older save.
    ss.update_store_settings(
        session, {"tax_rate": 0.28, "shipping_cost": 99.0}, actor_id=None
    )
    restored = settings_api.restore_store_policy(
        StoreSettingsRestoreRequest(audit_id=first.id), None, session, _STUB_USER
    )
    assert restored.tax_rate == 0.18
    assert restored.shipping_cost == 99.0  # untouched key keeps its value

    # The restore is itself audited and linked, so it can be undone too.
    trail = settings_api.get_store_history(session, _STUB_USER, limit=5)
    top = trail.entries[0]
    assert top.action == "settings.store_restored"
    assert [c.model_dump() for c in top.changes] == [
        {"key": "tax_rate", "before": 0.28, "after": 0.18}
    ]
    again, _ = ss.restore_values(session, top.audit_id)
    assert again == {"tax_rate": 0.28}


def test_12_restore_endpoint_rejects(session):
    ss.get_store_settings(session)
    with pytest.raises(HTTPException) as exc:
        settings_api.restore_store_policy(
            StoreSettingsRestoreRequest(audit_id=uuid4()), None, session, _STUB_USER
        )
    assert exc.value.status_code == 422


def test_13_percent_scale_contract_end_to_end(session):
    """Restocking fees are percent-scale DB → math → display; tax is fraction.

    Regression test for the admin-UI bug that rendered 5.0 as "500": the
    stored/fee/displayed contract is 5.0 in, 5% out. A ₹1500 confirmed
    cancellation costs exactly ₹75.00 (₹225.00 while processing).
    """
    from decimal import Decimal
    from types import SimpleNamespace

    from app.models.order import OrderStatus
    from app.services import refund_service

    ss.get_store_settings(session)  # seed from env (percent-scale)
    snap = ss.get_store_settings(session)
    assert snap.restocking_fee_pending == 0.0
    assert snap.restocking_fee_confirmed == 5.0
    assert snap.restocking_fee_processing == 15.0
    assert snap.tax_rate == 0.18  # the one fraction-scale field

    order = SimpleNamespace(grand_total=Decimal("1500.00"), refund_amount=None)
    calc = refund_service.calculate_refund(order, OrderStatus.CONFIRMED)
    assert calc["fee_percentage"] == 5.0
    assert calc["restocking_fee"] == Decimal("75.00")
    assert calc["refund_amount"] == Decimal("1425.00")

    processing = refund_service.calculate_refund(order, OrderStatus.PROCESSING)
    assert processing["fee_percentage"] == 15.0
    assert processing["restocking_fee"] == Decimal("225.00")

    # The admin save path stores raw percent values (no /100 division).
    ss.update_store_settings(session, {"restocking_fee_confirmed": 5.0}, actor_id=None)
    assert ss.get_store_settings(session).restocking_fee_confirmed == 5.0


def test_1_first_read_seeds_from_env(session):
    snap = ss.get_store_settings(session)
    assert snap.source == "database"
    assert snap.tax_rate == float(env_settings.TAX_RATE)
    assert snap.cod_max_order_value == float(env_settings.COD_MAX_ORDER_VALUE)


def test_2_sessionless_read_matches(session):
    ss.get_store_settings(session)  # warms the cache
    cached = ss.get_store_settings()
    assert cached.tax_rate == float(env_settings.TAX_RATE)


def test_3_update_takes_effect_immediately(session):
    ss.get_store_settings(session)
    row = ss.update_store_settings(session, {"tax_rate": 0.28}, actor_id=None)
    assert row.tax_rate == 0.28
    assert ss.get_store_settings().tax_rate == 0.28
    assert ss.get_store_settings(session).source == "database"


def test_4_partial_update_keeps_rest(session):
    ss.get_store_settings(session)
    ss.update_store_settings(session, {"shipping_cost": 99.0}, actor_id=None)
    snap = ss.get_store_settings(session)
    assert snap.shipping_cost == 99.0
    assert snap.tax_rate == float(env_settings.TAX_RATE)


def test_5_schema_rejects_bad_values():
    with pytest.raises(ValidationError):
        StoreSettingsUpdate(tax_rate=2.0)
    with pytest.raises(ValidationError):
        StoreSettingsUpdate(cod_fee=-5.0)
    with pytest.raises(ValidationError):
        StoreSettingsUpdate(restocking_fee_confirmed=150.0)
    with pytest.raises(ValidationError):
        StoreSettingsUpdate(refund_processing_days=0)
    # Valid partial payload passes.
    assert StoreSettingsUpdate(tax_rate=0.12).tax_rate == 0.12
