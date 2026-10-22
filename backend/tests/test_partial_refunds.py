from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.models.user import User
from app.models.address import Address
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.refund import Refund, RefundStatus
from app.models.email_outbox import EmailOutbox
from app.services.refund_service import process_refund, calculate_refund, fetch_refund_status
from app.api.v1.webhooks import _handle_refund_webhook


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    provider = Mock()
    provider.create_refund.side_effect = [
        {"status": "pending", "refund_id": "first"},
        {"status": "pending", "refund_id": "second"},
        {"status": "processed", "refund_id": "third"},
    ]
    monkeypatch.setattr("app.services.refund_service.get_payment_service_for_payment", lambda p: provider)
    with Session(engine) as s:
        user = User(email="partial@example.com", username="partial")
        s.add(user)
        s.flush()
        address = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="IN")
        s.add(address)
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=address.id,
                      billing_address_id=address.id, subtotal=Decimal("100"), grand_total=Decimal("100"),
                      status=OrderStatus.DELIVERED, payment_status="paid", payment_method="online")
        s.add(order)
        s.flush()
        payment = Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_partial",
                          provider_payment_intent="pay_partial", amount=Decimal("100"), status=PaymentStatus.SUCCEEDED)
        s.add(payment)
        s.commit()
        yield s, order, payment, provider
    engine.dispose()


def refund(s, order, key, amount):
    return process_refund(s, order, order.status, amount=Decimal(amount), idempotency_key=key)


def test_repeated_partial_refunds_keep_fulfillment_and_captured_payment(db):
    s, order, payment, provider = db
    refund(s, order, "a", "25")
    assert order.status == OrderStatus.DELIVERED and order.payment_status == "paid"
    assert payment.status == PaymentStatus.SUCCEEDED and order.can_refund
    refund(s, order, "b", "30")
    assert order.refund_amount == Decimal("55") and order.can_refund
    assert order.status == OrderStatus.DELIVERED
    assert provider.create_refund.call_count == 2
    replay = refund(s, order, "a", "25")
    assert replay["duplicate"] and order.refund_amount == Decimal("55")


def test_old_webhook_updates_its_ledger_and_waits_for_all_full_refunds(db):
    s, order, payment, _ = db
    refund(s, order, "a", "25")
    refund(s, order, "b", "75")
    assert order.payment_status == "refund_initiated"
    _handle_refund_webhook(s, "refund.processed", {"id": "first"})
    assert s.exec(select(Refund).where(Refund.provider_refund_id == "first")).one().provider_status == "processed"
    assert order.payment_status == "refund_initiated"
    _handle_refund_webhook(s, "refund.processed", {"id": "second"})
    assert order.payment_status == "refund_completed" and payment.status == PaymentStatus.REFUNDED
    _handle_refund_webhook(s, "refund.failed", {"id": "first"})
    assert order.refund_amount == Decimal("100") and order.payment_status == "refund_completed"


def test_failed_partial_releases_only_its_reserved_balance_once(db):
    s, order, payment, _ = db
    refund(s, order, "a", "25")
    refund(s, order, "b", "30")
    for _ in range(2):
        _handle_refund_webhook(s, "refund.failed", {"id": "first"})
    assert order.refund_amount == Decimal("30") and order.status == OrderStatus.DELIVERED
    assert order.can_refund and payment.status == PaymentStatus.SUCCEEDED
    assert s.exec(select(Refund).where(Refund.provider_refund_id == "first")).one().status == RefundStatus.FAILED
    refund(s, order, "c", "70")
    assert order.refund_amount == Decimal("100")


def test_completed_partial_does_not_terminate_order(db):
    s, order, payment, _ = db
    refund(s, order, "a", "25")
    _handle_refund_webhook(s, "refund.processed", {"id": "first"})
    assert order.status == OrderStatus.DELIVERED and order.payment_status == "paid"
    assert order.can_refund and payment.status == PaymentStatus.SUCCEEDED


def test_pending_and_completed_emails_use_individual_refund_amounts(db):
    s, order, _, _ = db
    refund(s, order, "a", "25")
    refund(s, order, "b", "30")
    _handle_refund_webhook(s, "refund.processed", {"id": "first"})
    rows = s.exec(select(EmailOutbox).order_by(EmailOutbox.created_at)).all()
    assert "₹25.00" in rows[0].html_content and "₹100.00" not in rows[0].html_content
    assert "₹30.00" in rows[1].html_content and "₹55.00" not in rows[1].html_content
    assert "₹25.00" in rows[2].html_content


def test_retained_fee_stays_fixed_and_does_not_mark_charge_wholly_refunded(db):
    s, order, payment, _ = db
    order.status = OrderStatus.CONFIRMED
    s.add(order)
    s.commit()
    refund(s, order, "a", "25")
    fee = order.restocking_fee
    order.status = OrderStatus.CANCELLED
    s.add(order)
    s.commit()
    assert calculate_refund(order, order.status, session=s)["restocking_fee"] == fee
    refund(s, order, "b", "100")
    assert order.refund_amount == Decimal("100") - fee and not order.can_refund
    assert payment.status == PaymentStatus.SUCCEEDED


def test_live_status_uses_own_provider_and_all_refund_ids(db):
    s, order, _, provider = db
    refund(s, order, "a", "25")
    refund(s, order, "b", "30")
    provider.get_refund_status.side_effect = lambda rid: {"status": "processed" if rid == "second" else "pending"}
    assert fetch_refund_status(order, s)["status"] == "pending"
    assert {call.args[0] for call in provider.get_refund_status.call_args_list} == {"first", "second"}


def test_failed_full_policy_refund_reopens_balance_without_losing_fee(db):
    s, order, payment, _ = db
    order.status = OrderStatus.CONFIRMED
    s.add(order)
    s.commit()
    refund(s, order, "full", "100")
    fee = order.restocking_fee
    assert order.status == OrderStatus.REFUNDED
    _handle_refund_webhook(s, "refund.failed", {"id": "first"})
    assert order.refund_amount == 0 and order.can_refund
    assert order.payment_status == "refund_failed" and payment.status == PaymentStatus.SUCCEEDED
    assert calculate_refund(order, order.status, session=s)["refund_amount"] == Decimal("100") - fee
    refund(s, order, "retry", "100")
    assert order.refund_amount == Decimal("100") - fee


@pytest.mark.parametrize("provider_status,expected_status,amount", [
    ("processed", "refund_completed", Decimal("100")),
    ("failed", "refund_failed", Decimal("0")),
])
def test_reconciliation_updates_existing_inflight_rows(db, provider_status, expected_status, amount):
    from fastapi import Request
    from app.api.v1.admin.refunds import reconcile_order_refunds
    from app.models.user import User
    s, order, payment, provider = db
    refund(s, order, "full", "100")
    provider.get_charge_refund_state.return_value = {
        "refunds": [{"id": "first", "amount": 100, "status": provider_status}],
        "charge_total": 100, "refunded_total": float(amount),
    }
    request = Request({"type": "http", "headers": []})
    result = reconcile_order_refunds(order.id, s, request, s.get(User, order.user_id))
    assert result["synced_rows"] == 1
    assert order.payment_status == expected_status and order.refund_amount == amount
    assert payment.status == (PaymentStatus.REFUNDED if amount else PaymentStatus.SUCCEEDED)
    assert reconcile_order_refunds(order.id, s, request, s.get(User, order.user_id))["synced_rows"] == 0


def test_old_failed_refund_does_not_poison_successful_retry_live_status(db):
    s, order, _, provider = db
    refund(s, order, "a", "25")
    _handle_refund_webhook(s, "refund.failed", {"id": "first"})
    refund(s, order, "b", "25")
    provider.get_refund_status.side_effect = lambda rid: {"status": "failed" if rid == "first" else "processed"}
    assert fetch_refund_status(order, s)["status"] == "processed"


def test_reconciliation_conflict_rolls_back_other_provider_updates(db):
    from fastapi import Request, HTTPException
    from app.api.v1.admin.refunds import reconcile_order_refunds
    from app.models.user import User
    s, order, _, provider = db
    refund(s, order, "a", "25")
    refund(s, order, "b", "30")
    provider.get_charge_refund_state.return_value = {"refunds": [
        {"id": "first", "amount": 25, "status": "processed"},
        {"id": "second", "amount": 80, "status": "processed"},
    ]}
    with pytest.raises(HTTPException) as exc:
        reconcile_order_refunds(order.id, s, Request({"type": "http", "headers": []}), s.get(User, order.user_id))
    assert exc.value.status_code == 409
    assert order.refund_amount == Decimal("55")
    assert all(row.provider_status == "pending" for row in s.exec(select(Refund)).all())
