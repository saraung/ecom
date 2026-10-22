"""Functional test for the new refund status flow (refund_initiated / refund_completed / refund_failed)."""
import sys
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from sqlmodel import SQLModel, create_engine, Session

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus, PaymentProvider
from app.models.address import Address

from app.services.refund_service import process_refund
from app.api.v1.webhooks import _handle_refund_webhook

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


def setup_db():
    SQLModel.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        user = User(
            username="tester", email="tester@test.com", full_name="Test User",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)

        addr = Address(
            user_id=user.id,
            label="Home", line1="1 Main St", city="Mumbai", state="MH",
            postal_code="400001", country="IN", is_default=True,
        )
        s.add(addr)
        s.commit()
        s.refresh(addr)

        order = Order(
            order_number="ORD-TEST-1001",
            user_id=user.id,
            shipping_address_id=addr.id,
            billing_address_id=addr.id,
            subtotal=Decimal("1000.00"),
            discount_total=Decimal("0"),
            tax_total=Decimal("180.00"),
            shipping_total=Decimal("50.00"),
            grand_total=Decimal("1230.00"),
            payment_method="online",
            payment_status="paid",
            status=OrderStatus.CONFIRMED,
            placed_at=datetime.now(timezone.utc),
        )
        s.add(order)
        s.commit()
        s.refresh(order)

        payment = Payment(
            order_id=order.id,
            provider=PaymentProvider.RAZORPAY,
            provider_payment_id="order_rzp_test_123",
            provider_payment_intent="pay_rzp_test_123",
            amount=Decimal("1230.00"),
            currency="INR",
            status=PaymentStatus.SUCCEEDED,
        )
        s.add(payment)
        s.commit()
        return user.id, order.id


def new_paid_order(s):
    """Create a fresh paid online order + payment; returns the order."""
    addr = Address(
        user_id=USER_ID,
        label="Home2", line1="2 Main St", city="Mumbai", state="MH",
        postal_code="400001", country="IN", is_default=False,
    )
    s.add(addr)
    s.commit()
    s.refresh(addr)

    order = Order(
        order_number=f"ORD-TEST-{uuid4().hex[:8]}",
        user_id=USER_ID,
        shipping_address_id=addr.id,
        billing_address_id=addr.id,
        subtotal=Decimal("1000.00"),
        discount_total=Decimal("0"),
        tax_total=Decimal("180.00"),
        shipping_total=Decimal("50.00"),
        grand_total=Decimal("1230.00"),
        payment_method="online",
        payment_status="paid",
        status=OrderStatus.CONFIRMED,
        placed_at=datetime.now(timezone.utc),
    )
    s.add(order)
    s.commit()
    s.refresh(order)

    payment = Payment(
        order_id=order.id,
        provider=PaymentProvider.RAZORPAY,
        provider_payment_id="order_rzp_new",
        provider_payment_intent="pay_rzp_new",
        amount=Decimal("1230.00"),
        currency="INR",
        status=PaymentStatus.SUCCEEDED,
    )
    s.add(payment)
    s.commit()
    return order


def test_1_refund_service_sets_initiated_when_pending():
    print("\n=== TEST 1: process_refund -> refund_initiated (pending provider status) ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        fake_result = {
            "status": "pending",
            "refund_id": "rfnd_test_pending_001",
            "payment_id": "pay_rzp_test_123",
            "amount": 1000.00,
        }
        with patch("app.services.refund_service.get_payment_service_for_payment") as mocked:
            svc = mocked.return_value
            svc.create_refund.return_value = fake_result
            result = process_refund(s, order, OrderStatus.CONFIRMED, "Changed my mind")
            assert result["processed"] is True
            assert result["payment_status"] == "refund_initiated", result
            assert result["refund_id"] == "rfnd_test_pending_001"
        s.refresh(order)
        assert order.payment_status == "refund_initiated"
        assert order.refund_id == "rfnd_test_pending_001"
        assert order.refunded_at is not None
        assert order.status == OrderStatus.REFUNDED, f"Expected REFUNDED, got {order.status}"
        print("  ✅ order.payment_status =", order.payment_status)
        print("  ✅ order.status =", order.status.value)
        print("  ✅ result has payment_status:", result["payment_status"])


def test_2_refund_service_sets_completed_when_processed():
    print("\n=== TEST 2: process_refund -> refund_completed (processed provider status / dummy) ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        fake_result = {
            "status": "processed",
            "refund_id": "rfnd_test_processed_001",
            "payment_id": "pay_rzp_test_123",
            "amount": 1000.00,
        }
        with patch("app.services.refund_service.get_payment_service_for_payment") as mocked:
            svc = mocked.return_value
            svc.create_refund.return_value = fake_result
            result = process_refund(s, order, OrderStatus.CONFIRMED, "Duplicate order")
            assert result["processed"] is True
            assert result["payment_status"] == "refund_completed", result
        s.refresh(order)
        assert order.payment_status == "refund_completed"
        assert order.status == OrderStatus.REFUNDED, f"Expected REFUNDED, got {order.status}"
        print("  ✅ order.payment_status =", order.payment_status)
        print("  ✅ order.status =", order.status.value)
def test_3_webhook_refund_processed():
    print("\n=== TEST 3: webhook refund.processed -> refund_completed ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        # simulate live-mode state: initiated, awaiting webhook
        order.payment_status = "refund_initiated"
        order.refund_id = "rfnd_webhook_abcd"
        s.add(order)
        s.commit()

        _handle_refund_webhook(
            s, "refund.processed",
            {"id": "rfnd_webhook_abcd", "status": "processed", "amount": 123000},
        )
        s.refresh(order)
        assert order.payment_status == "refund_completed", order.payment_status
        assert order.status == OrderStatus.REFUNDED, f"Expected REFUNDED, got {order.status}"
        print("  ✅ order.payment_status =", order.payment_status)
        print("  ✅ order.status =", order.status.value)


def test_4_webhook_refund_failed():
    print("\n=== TEST 4: webhook refund.failed -> refund_failed ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        order.payment_status = "refund_initiated"
        order.refund_id = "rfnd_webhook_efgh"
        s.add(order)
        s.commit()

        _handle_refund_webhook(s, "refund.failed", {"id": "rfnd_webhook_efgh", "status": "failed"})
        s.refresh(order)
        assert order.payment_status == "refund_failed", order.payment_status
        print("  ✅ order.payment_status =", order.payment_status)


def test_5_webhook_unknown_refund_id_no_crash():
    print("\n=== TEST 5: webhook with unknown refund_id -> no crash ===")
    with Session(ENGINE) as s:
        _handle_refund_webhook(s, "refund.processed", {"id": "rfnd_does_not_exist"})
        print("  ✅ no exception raised")


def test_6_duplicate_processed_event_is_idempotent():
    print("\n=== TEST 6: duplicate refund.processed is idempotent ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        order.payment_status = "refund_initiated"
        order.refund_id = "rfnd_webhook_idem_001"
        s.add(order)
        s.commit()
        _handle_refund_webhook(s, "refund.processed", {"id": "rfnd_webhook_idem_001"})
        _handle_refund_webhook(s, "refund.processed", {"id": "rfnd_webhook_idem_001"})
        s.refresh(order)
        assert order.payment_status == "refund_completed"
        print("  ✅ stays refund_completed, no error on duplicate")


USER_ID = None
ORDER_ID = None
_SETUP_DONE = False


def _ensure_setup():
    """Seed the in-memory DB once (works for both `python file.py` and pytest)."""
    global USER_ID, ORDER_ID, _SETUP_DONE
    if not _SETUP_DONE:
        USER_ID, ORDER_ID = setup_db()
        _SETUP_DONE = True
        print("Seeded DB (user=%s, order=%s)" % (USER_ID, ORDER_ID))


def test_7_per_payment_routing_razorpay_record_under_stripe_settings():
    """Razorpay payment row routes to Razorpay even when global = stripe."""
    print("\n=== TEST 7: per-payment routing (razorpay row, stripe settings) ===")
    from unittest.mock import MagicMock
    from app.services import refund_service as rs_mod

    razorpay_svc = MagicMock()
    razorpay_svc.get_payment_id_for_order = MagicMock(
        return_value="pay_TWckya4DzCJzw3"
    )
    razorpay_svc.create_refund.return_value = {
        "status": "processed",
        "refund_id": "rfnd_routed_rzp_001",
        "payment_id": "pay_TWckya4DzCJzw3",
        "amount": 1169.5,
    }
    stripe_svc = MagicMock()
    stripe_svc.get_payment_id_for_order = MagicMock(
        side_effect=Exception("No such payment_intent")
    )
    stripe_svc.create_refund.side_effect = AssertionError(
        "Stripe must NOT be called for a Razorpay payment"
    )

    def _route(payment=None, **kwargs):
        name = getattr(getattr(payment, "provider", None), "value",
                       str(getattr(payment, "provider", ""))).lower()
        if name == "razorpay":
            return razorpay_svc
        return stripe_svc

    with Session(ENGINE) as s:
        order = new_paid_order(s)
        # Simulate ORD-20260901085753: order-level id stored, charge id NOT
        # yet settled on the row.
        from sqlmodel import select as _select
        pay = s.exec(
            _select(Payment).where(Payment.order_id == order.id)
        ).first()
        pay.provider = PaymentProvider.RAZORPAY
        pay.provider_payment_id = "order_TWckp9KZO8kGBb"
        pay.provider_payment_intent = None
        s.add(pay)
        s.commit()
        s.refresh(order)

        with patch.object(
            rs_mod, "get_payment_service_for_payment", side_effect=_route
        ), patch.object(
            rs_mod, "get_payment_service", return_value=stripe_svc
        ):
            result = process_refund(s, order, OrderStatus.CONFIRMED, "Changed my mind")
            assert result["processed"] is True, result
            assert result["refund_id"] == "rfnd_routed_rzp_001"
            razorpay_svc.create_refund.assert_called_once()
            args, _ = razorpay_svc.create_refund.call_args
            assert args[0] == "pay_TWckya4DzCJzw3", args
            assert stripe_svc.create_refund.call_count == 0
            print("  ✅ routed to Razorpay, refunded pay_TWckya4DzCJzw3")


def test_8_cod_payment_refused_without_psp_call():
    """COD rows never touch a PSP — clear 400-style message instead."""
    print("\n=== TEST 8: COD payment refused ===")
    with Session(ENGINE) as s:
        order = new_paid_order(s)
        from sqlmodel import select as _select
        pay = s.exec(
            _select(Payment).where(Payment.order_id == order.id)
        ).first()
        pay.provider = PaymentProvider.COD
        s.add(pay)
        s.commit()
        s.refresh(order)
        result = process_refund(
            s, order, OrderStatus.CONFIRMED, "Changed my mind",
            idempotency_key=f"test-cod-{uuid4().hex}",
        )
        assert result["processed"] is False, result
        assert "Cash on Delivery" in result["message"], result
        print("  ✅ COD refused:", result["message"])


def run_all():
    test_1_refund_service_sets_initiated_when_pending()
    test_2_refund_service_sets_completed_when_processed()
    test_7_per_payment_routing_razorpay_record_under_stripe_settings()
    test_8_cod_payment_refused_without_psp_call()
    test_3_webhook_refund_processed()
    test_4_webhook_refund_failed()
    test_5_webhook_unknown_refund_id_no_crash()
    test_6_duplicate_processed_event_is_idempotent()
    print("\n🎉 ALL REFUND FLOW TESTS PASSED")


_ensure_setup()

if __name__ == "__main__":
    run_all()