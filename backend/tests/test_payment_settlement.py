"""Exercise callbacks and signed-event reconciliation through real DB state."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from starlette.requests import Request

import app.models  # noqa: F401
from app.api.v1 import payments, webhooks
from app.models.address import Address
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.user import User
from app.schemas.payment import PaymentConfirmRequest


@pytest.fixture
def data(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(payments.settings, "SENDGRID_API_KEY", None)
    with Session(engine) as s:
        user = User(email="settle@example.com", username="settle", password_hash="x")
        s.add(user)
        s.flush()
        addr = Address(user_id=user.id, line1="1 Main", city="Mumbai", state="MH",
                       postal_code="400001", country="India")
        s.add(addr)
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id,
                      shipping_address_id=addr.id, billing_address_id=addr.id,
                      subtotal=Decimal("100"), grand_total=Decimal("100"),
                      payment_method="online")
        s.add(order)
        s.flush()
        payment = Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_test",
                          amount=Decimal("100"), currency="INR")
        s.add(payment)
        s.commit()
        ids = user.id, order.id, payment.id
    provider = Mock()
    provider.confirm_payment.return_value = {"status": "succeeded", "is_dummy": False, "method": "upi"}
    provider.get_payment_id_for_order.return_value = "pay_verified"
    # Patch the routing function where used by either old or corrected code.
    monkeypatch.setattr(payments, "get_payment_service", lambda: provider)
    monkeypatch.setattr("app.services.payment_service.get_payment_service_for_payment", lambda p: provider)
    monkeypatch.setattr("app.services.refund_service.get_payment_service_for_payment", lambda p: provider)
    yield engine, ids, provider
    engine.dispose()


def _confirm(s, ids):
    return payments.confirm_payment(PaymentConfirmRequest(payment_intent_id="order_test",
                                    transaction_id="pay_untrusted"), s, s.get(User, ids[0]))


def _event(s, monkeypatch, event_type):
    provider = SimpleNamespace(handle_webhook=lambda *a: {
        "event_type": event_type, "payment_id": "order_test", "transaction_id": "pay_verified",
        "payment_method": "upi"})
    monkeypatch.setattr(webhooks, "get_payment_service", lambda: provider)
    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}
    req = Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)
    return asyncio.run(webhooks.payment_webhook(req, s))


@pytest.mark.parametrize("state", [OrderStatus.PROCESSING, OrderStatus.SHIPPED,
                                    OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED, OrderStatus.RTO])
def test_callback_preserves_fulfillment_and_trusted_instrument(data, state):
    engine, ids, provider = data
    with Session(engine) as s:
        order = s.get(Order, ids[1])
        order.status = state
        s.add(order)
        s.commit()
        result = _confirm(s, ids)
        assert s.get(Order, ids[1]).status == state
        assert result.payment_method == "upi"
        assert result.transaction_id == "pay_verified"


def test_duplicate_callback_and_webhook_do_not_change_paid_at(data, monkeypatch):
    engine, ids, provider = data
    with Session(engine) as s:
        payment = _confirm(s, ids)
        paid_at = payment.paid_at
        _event(s, monkeypatch, "payment.succeeded")
        _confirm(s, ids)
        assert s.get(Payment, ids[2]).paid_at == paid_at
        assert provider.confirm_payment.call_count == 1


def test_webhook_repairs_legacy_payment_only_commit(data, monkeypatch):
    engine, ids, _ = data
    with Session(engine) as s:
        payment = s.get(Payment, ids[2])
        payment.status = PaymentStatus.SUCCEEDED
        payment.paid_at = datetime.now(timezone.utc)
        s.add(payment)
        s.commit()
        _event(s, monkeypatch, "payment.succeeded")
        assert s.get(Order, ids[1]).status == OrderStatus.CONFIRMED
        assert s.get(Order, ids[1]).payment_status == "paid"


def test_confirmation_is_one_commit_and_rollback_on_commit_error(data):
    engine, ids, _ = data
    with Session(engine) as s:
        calls = []
        def fail(session):
            calls.append(True)
            raise RuntimeError("database unavailable")
        event.listen(s, "before_commit", fail)
        with pytest.raises(RuntimeError, match="database unavailable"):
            _confirm(s, ids)
        event.remove(s, "before_commit", fail)
        s.commit()
        assert len(calls) == 1
    with Session(engine) as s:
        assert s.get(Payment, ids[2]).status == PaymentStatus.PENDING
        assert s.get(Order, ids[1]).payment_status == "pending"


def test_pending_confirmation_does_not_mark_failed(data):
    engine, ids, provider = data
    provider.confirm_payment.return_value = {"status": "pending"}
    with Session(engine) as s:
        with pytest.raises(HTTPException) as exc:
            _confirm(s, ids)
        assert exc.value.status_code == 409
        assert s.get(Payment, ids[2]).status == PaymentStatus.PENDING


def test_refunded_payment_and_order_ignore_late_capture_and_failure(data, monkeypatch):
    engine, ids, _ = data
    with Session(engine) as s:
        order, payment = s.get(Order, ids[1]), s.get(Payment, ids[2])
        order.status, order.payment_status = OrderStatus.REFUNDED, "refund_completed"
        payment.status = PaymentStatus.REFUNDED
        s.add_all([order, payment])
        s.commit()
        _confirm(s, ids)
        _event(s, monkeypatch, "payment.succeeded")
        _event(s, monkeypatch, "payment.failed")
        assert s.get(Payment, ids[2]).status == PaymentStatus.REFUNDED
        assert s.get(Order, ids[1]).payment_status == "refund_completed"


def test_completed_refund_cannot_be_downgraded_by_failed_event(data):
    engine, ids, _ = data
    with Session(engine) as s:
        order = s.get(Order, ids[1])
        order.status, order.payment_status, order.refund_id = OrderStatus.REFUNDED, "refund_completed", "rfnd_test"
        s.add(order)
        s.commit()
        webhooks._handle_refund_webhook(s, "refund.failed", {"id": "rfnd_test"})
        assert s.get(Order, ids[1]).payment_status == "refund_completed"


@pytest.mark.parametrize("via_webhook", [False, True])
def test_cancelled_late_capture_refunds_once_without_reopening(data, monkeypatch, via_webhook):
    engine, ids, provider = data
    provider.create_refund.return_value = {"status": "processed", "refund_id": "rfnd_late"}
    with Session(engine) as s:
        order = s.get(Order, ids[1])
        order.status, order.payment_status = OrderStatus.CANCELLED, "cancelled"
        s.add(order)
        s.commit()
        for _ in range(2):
            _event(s, monkeypatch, "payment.succeeded") if via_webhook else _confirm(s, ids)
        assert provider.create_refund.call_count == 1
        assert s.get(Order, ids[1]).status == OrderStatus.REFUNDED
        assert s.get(Payment, ids[2]).status == PaymentStatus.REFUNDED


def test_failed_late_refund_is_retryable_even_when_payment_already_succeeded(data, monkeypatch):
    engine, ids, provider = data
    provider.create_refund.side_effect = [
        {"status": "failed", "error": "temporary outage"},
        {"status": "processed", "refund_id": "rfnd_retry"},
    ]
    provider.get_charge_refund_state.return_value = None
    with Session(engine) as s:
        order = s.get(Order, ids[1])
        order.status, order.payment_status = OrderStatus.CANCELLED, "cancelled"
        s.add(order)
        s.commit()
        with pytest.raises(HTTPException) as exc:
            _event(s, monkeypatch, "payment.succeeded")
        assert exc.value.status_code == 503
        assert s.get(Order, ids[1]).status == OrderStatus.CANCELLED
        assert s.get(Payment, ids[2]).status == PaymentStatus.SUCCEEDED
        _event(s, monkeypatch, "payment.succeeded")
        assert s.get(Order, ids[1]).payment_status == "refund_completed"
        assert provider.create_refund.call_count == 2


def test_late_failed_event_does_not_cancel_paid_order(data, monkeypatch):
    engine, ids, _ = data
    with Session(engine) as s:
        _confirm(s, ids)
        _event(s, monkeypatch, "payment.failed")
        assert s.get(Order, ids[1]).status == OrderStatus.CONFIRMED
        assert s.get(Payment, ids[2]).status == PaymentStatus.SUCCEEDED


@pytest.mark.parametrize("status,expected", [("succeeded", "refund.processed"),
                                             ("failed", "refund.failed"),
                                             ("pending", "refund.pending")])
def test_stripe_refund_events_do_not_complete_pending_money(status, expected):
    from app.services.stripe_service import StripePaymentService
    service = object.__new__(StripePaymentService)
    result = service._normalize_event({"type": "refund.updated", "data": {"object": {
        "id": "re_test", "status": status, "payment_intent": "pi_test"}}})
    assert result["event_type"] == expected
