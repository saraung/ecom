from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.models.address import Address
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.refund import Refund
from app.models.user import User
from app.services.payment_service import DummyPaymentService
from app.services.refund_service import process_refund
from app.services.razorpay_service import RazorpayPaymentService
from app.services.stripe_service import StripePaymentService


class Gateway(DummyPaymentService):
    requires_refund_reconciliation = True
    def __init__(self):
        self.refunds, self.calls = [], 0
        self.lost = False
    def get_charge_refund_state(self, payment_id):
        return {"refunds": self.refunds, "charge_total": 100, "currency": "INR"}
    def create_refund(self, payment_id, amount=None, notes=None):
        self.calls += 1
        row = {"id": "rfnd_recovered", "amount": amount, "status": "processed", "notes": notes}
        self.refunds.append(row)
        if self.lost:
            return {"status": "unknown"}
        return {"status": "processed", "refund_id": row["id"]}


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    gateway = Gateway()
    monkeypatch.setattr("app.services.refund_service.get_payment_service_for_payment", lambda p: gateway)
    with Session(engine) as s:
        user = User(email="recovery@example.com", username="recovery")
        s.add(user)
        s.flush()
        addr = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add(addr)
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=addr.id,
                      billing_address_id=addr.id, subtotal=Decimal("100"), grand_total=Decimal("100"),
                      status=OrderStatus.CANCELLED, payment_method="online", payment_status="paid")
        s.add(order)
        s.flush()
        s.add(Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_recovery",
                      provider_payment_intent="pay_recovery", amount=Decimal("100"), status=PaymentStatus.SUCCEEDED))
        s.commit()
        yield s, order, gateway
    engine.dispose()


def test_external_success_then_commit_failure_replays_without_moving_money_twice(db):
    s, order, gateway = db
    def fail(session):
        raise RuntimeError("DB commit lost")
    event.listen(s, "before_commit", fail)
    with pytest.raises(RuntimeError):
        process_refund(s, order, OrderStatus.PENDING, idempotency_key="stable")
    event.remove(s, "before_commit", fail)
    assert s.exec(select(Refund)).all() == []
    assert order.payment_status == "paid"
    result = process_refund(s, order, OrderStatus.PENDING, idempotency_key="stable")
    assert result["processed"] and result["refund_id"] == "rfnd_recovered"
    assert gateway.calls == 1
    assert s.exec(select(Refund)).one().amount == Decimal("100")


def test_ambiguous_gateway_response_rollback_and_same_key_recovery(db):
    s, order, gateway = db
    gateway.lost = True
    with pytest.raises(HTTPException) as exc:
        process_refund(s, order, OrderStatus.PENDING, idempotency_key="lost")
    assert exc.value.status_code == 503
    assert s.exec(select(Refund)).all() == []
    process_refund(s, order, OrderStatus.PENDING, idempotency_key="lost")
    assert gateway.calls == 1


def test_different_key_cannot_double_refund_unrecorded_money(db):
    s, order, gateway = db
    gateway.lost = True
    with pytest.raises(HTTPException):
        process_refund(s, order, OrderStatus.PENDING, idempotency_key="first", amount=Decimal("25"))
    with pytest.raises(HTTPException) as exc:
        process_refund(s, order, OrderStatus.PENDING, idempotency_key="second", amount=Decimal("25"))
    assert exc.value.status_code == 503 and gateway.calls == 1


def test_provider_lookup_outage_prevents_first_money_movement(db, monkeypatch):
    s, order, gateway = db
    monkeypatch.setattr(gateway, "get_charge_refund_state", lambda p: None)
    with pytest.raises(HTTPException):
        process_refund(s, order, OrderStatus.PENDING)
    assert gateway.calls == 0


def test_fully_refunded_idempotent_replay_is_still_processed(db):
    s, order, gateway = db
    process_refund(s, order, OrderStatus.PENDING, idempotency_key="complete")
    result = process_refund(s, order, OrderStatus.PENDING, idempotency_key="complete")
    assert result["processed"] and result["duplicate"] and result["amount"] == Decimal("100")
    assert gateway.calls == 1


def test_razorpay_refund_receipt_and_transport_ambiguity(monkeypatch):
    service = RazorpayPaymentService()
    service.is_configured = True
    service.client = Mock()
    service.client.payment.refund.return_value = {"id": "rfnd_test", "amount": 10000, "status": "processed"}
    service.create_refund("pay_test", 100, {"refund_key": "rf-stable"})
    assert service.client.payment.refund.call_args.args[1]["receipt"] == "rf-stable"
    service.client.payment.refund.side_effect = TimeoutError("lost")
    assert service.create_refund("pay_test", 100, {"refund_key": "rf-stable"})["status"] == "unknown"


def test_stripe_refund_native_idempotency(monkeypatch):
    service = StripePaymentService()
    service.is_configured = True
    send = Mock(return_value=SimpleNamespace(id="re_test", amount=10000, status="succeeded"))
    monkeypatch.setattr("app.services.stripe_service.stripe.Refund.create", send)
    service.create_refund("ch_test", 100, {"refund_key": "rf-stable"})
    assert send.call_args.kwargs["idempotency_key"] == "rf-stable"


def test_postgres_concurrent_refund_replay_moves_money_once(postgres_engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from tests.test_payment_creation import seed
    _, oid = seed(postgres_engine)
    with Session(postgres_engine) as s:
        order = s.get(Order, oid)
        order.status, order.payment_status = OrderStatus.CANCELLED, "paid"
        s.add(order)
        s.add(Payment(order_id=oid, provider="razorpay", provider_payment_id="order_pg",
                      provider_payment_intent="pay_pg", amount=Decimal("100"), status=PaymentStatus.SUCCEEDED))
        s.commit()
    gateway = Gateway()
    started, release = Event(), Event()
    original = gateway.create_refund
    def outbound(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    gateway.create_refund = outbound
    monkeypatch.setattr("app.services.refund_service.get_payment_service_for_payment", lambda p: gateway)
    def call():
        with Session(postgres_engine) as s:
            return process_refund(s, s.get(Order, oid), OrderStatus.PENDING, idempotency_key="pg-stable")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call)
        assert started.wait(10)
        second = pool.submit(call)
        release.set()
        assert first.result(timeout=15)["processed"] and second.result(timeout=15)["processed"]
    assert gateway.calls == 1
