from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from tests.test_inventory_release import seed
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus, PaymentProvider
from app.models.admin_audit import AdminAuditLog
from app.api.v1.admin.cod import collect_cod_payment, get_pending_cod_orders
from app.api.v1.webhooks import process_tracking_event
from app.repositories.commerce import settled_sale


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    uid, oid, _ = seed(engine)
    with Session(engine) as s:
        yield s, s.get(Order, oid), s.get(User, uid)
    engine.dispose()


def test_delivered_webhook_auto_collects_cod_payment(db):
    """DELIVERED webhook for a COD order auto-records the COD payment idempotently."""
    s, order, user = db
    process_tracking_event(s, {"awb": order.awb_code, "current_status": "DELIVERED"})
    assert order.status == OrderStatus.DELIVERED
    assert order.payment_status == "paid"
    assert s.exec(select(Order).where(settled_sale())).one().id == order.id
    payment = s.exec(select(Payment)).one()
    assert payment.provider == PaymentProvider.COD and payment.status == PaymentStatus.SUCCEEDED
    assert payment.amount == Decimal("200") and payment.paid_at is not None
    assert payment.payment_metadata["source"] == "webhook"
    assert s.exec(select(AdminAuditLog)).one().action == "cod.collected"
    # Duplicate DELIVERED webhook is ignored, no second payment.
    process_tracking_event(s, {"awb": order.awb_code, "current_status": "DELIVERED", "date": "later"})
    assert len(s.exec(select(Payment)).all()) == 1
    # Explicit collect after auto-collect returns 409.
    with pytest.raises(HTTPException) as exc:
        collect_cod_payment(order.id, s, user)
    assert exc.value.status_code == 409


def test_delivered_webhook_ignores_non_cod_order(db):
    """A delivered online-paid order must never gain a COD payment."""
    s, order, _ = db
    order.payment_method = "razorpay"
    order.payment_status = "paid"
    s.add(order)
    s.commit()
    process_tracking_event(s, {"awb": order.awb_code, "current_status": "DELIVERED"})
    assert order.status == OrderStatus.DELIVERED
    assert order.payment_status == "paid"
    assert not s.exec(select(Payment)).all()
    assert not s.exec(select(AdminAuditLog).where(AdminAuditLog.action == "cod.collected")).all()


def test_non_delivered_webhook_does_not_collect_cod(db):
    """In-transit scans must not create cash; only DELIVERED does."""
    s, order, _ = db
    process_tracking_event(s, {"awb": order.awb_code, "current_status": "IN TRANSIT"})
    assert order.status == OrderStatus.SHIPPED
    assert order.payment_status == "cod_pending"
    assert not s.exec(select(Payment)).all()


def test_manual_collection_audits_admin_actor(db):
    """The manual endpoint records the acting admin and marks source=admin."""
    s, order, user = db
    order.status = OrderStatus.DELIVERED
    order.payment_status = "cod_pending"
    s.add(order)
    s.commit()
    collect_cod_payment(order.id, s, user)
    payment = s.exec(select(Payment)).one()
    assert payment.payment_metadata["source"] == "admin"
    assert payment.payment_metadata["collected_by"] == str(user.id)
    assert payment.payment_metadata["collected_by_email"] == user.email
    audit = s.exec(select(AdminAuditLog).where(AdminAuditLog.action == "cod.collected")).one()
    assert audit.actor_id == user.id
    assert audit.after["source"] == "admin"


def test_webhook_collection_audits_system_actor(db):
    """Auto-collection is attributable to the webhook, not an admin."""
    s, order, _ = db
    process_tracking_event(s, {"awb": order.awb_code, "current_status": "DELIVERED"})
    audit = s.exec(select(AdminAuditLog).where(AdminAuditLog.action == "cod.collected")).one()
    assert audit.actor_id is None
    assert audit.after["source"] == "webhook"
    payment = s.exec(select(Payment)).one()
    assert payment.payment_metadata["collected_by_email"] == "shiprocket-webhook"


@pytest.mark.parametrize("status", [OrderStatus.CONFIRMED, OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.RTO, OrderStatus.REFUNDED])
def test_collection_rejects_not_delivered_states(db, status):
    s, order, user = db
    order.status = status
    s.add(order)
    s.commit()
    with pytest.raises(HTTPException):
        collect_cod_payment(order.id, s, user)
    assert not s.exec(select(Payment)).all()
    if status in (OrderStatus.CANCELLED, OrderStatus.RTO, OrderStatus.REFUNDED):
        assert get_pending_cod_orders(s, user)["count"] == 0


def test_collection_and_audit_roll_back_together(db):
    s, order, user = db
    # Set up as delivered but NOT collected (no webhook auto-collect here).
    order.status = OrderStatus.DELIVERED
    order.payment_status = "cod_pending"
    s.add(order)
    s.commit()
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO admin_audit_log"):
            raise RuntimeError("audit unavailable")
    event.listen(s.bind, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            collect_cod_payment(order.id, s, user)
    finally:
        event.remove(s.bind, "before_cursor_execute", fail)
    s.rollback()
    s.expire_all()
    assert order.payment_status == "cod_pending"
    assert not s.exec(select(Payment)).all()


def test_cod_truth_migration_preserves_real_collection(db):
    s, order, user = db
    # Order marked paid but with NO COD payment record (inconsistent pre-migration state).
    order.status = OrderStatus.DELIVERED
    order.payment_method = "cod"
    order.payment_status = "paid"
    s.add(order)
    s.commit()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/t5b6c7d8e9f0_cod_collection_truth.py"
    spec = importlib.util.spec_from_file_location("cod_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with s.bind.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
    s.expire_all()
    # No COD payment record exists, so the migration corrects paid -> cod_pending.
    assert order.payment_status == "cod_pending"
    # Collect now creates a real COD payment.
    collect_cod_payment(order.id, s, user)
    with s.bind.begin() as conn:
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
    s.expire_all()
    # A real COD payment now exists, so migration keeps payment_status = paid.
    assert order.payment_status == "paid"
    payments = s.exec(select(Payment).where(Payment.order_id == order.id)).all()
    assert len(payments) == 1
    assert payments[0].provider == PaymentProvider.COD


def test_postgres_concurrent_collection_records_cash_once(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    uid, oid, _ = seed(postgres_engine)
    with Session(postgres_engine) as s:
        order = s.get(Order, oid)
        order.status = OrderStatus.DELIVERED
        s.add(order)
        s.commit()
    barrier = Barrier(2)
    def collect():
        with Session(postgres_engine) as s:
            user = s.get(User, uid)
            stale = s.get(Order, oid)
            barrier.wait(timeout=10)
            try:
                collect_cod_payment(stale.id, s, user)
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(collect) for _ in range(2)]
        # The loser observes payment_status="paid" and gets 409 Conflict.
        assert sorted(call.result(timeout=15) for call in calls) == [200, 409]
    with Session(postgres_engine) as s:
        assert len(s.exec(select(Payment)).all()) == 1
