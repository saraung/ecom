"""Shared replay-safe local settlement for callbacks and provider events."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.services.email_outbox import enqueue_order_email


def _lock(session: Session, payment: Payment):
    # All payment events serialize on the order first, including multiple attempts.
    order = session.execute(
        select(Order).where(Order.id == payment.order_id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().one()
    payment = session.execute(
        select(Payment).where(Payment.id == payment.id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().one()
    return order, payment


def settle_payment(session: Session, payment: Payment, instrument=None, provider_payment_id=None):
    """Repair legacy half-settlements; never re-open fulfillment/refund states.

    Late captured money on a cancelled order follows the existing zero-fee
    refund path. A rejected refund is persisted for attention and returns 503
    so provider replay can retry it rather than silently dropping recovery.
    """
    send_confirmation = False
    refund_failed = False
    try:
        order, payment = _lock(session, payment)
        if (payment.status == PaymentStatus.REFUNDED
                or order.status == OrderStatus.REFUNDED
                or order.payment_status.startswith("refund_")):
            return payment
        if order.payment_method == "cod":
            raise HTTPException(400, "Cash on Delivery orders cannot be confirmed online")

        if payment.status != PaymentStatus.SUCCEEDED:
            payment.status = PaymentStatus.SUCCEEDED
            payment.paid_at = payment.paid_at or datetime.now(timezone.utc)
        if not payment.provider_payment_intent and provider_payment_id:
            payment.provider_payment_intent = provider_payment_id
        if not payment.payment_method or payment.payment_method == "online":
            payment.payment_method = instrument or payment.payment_method
        session.add(payment)

        if order.status == OrderStatus.CANCELLED:
            from app.services.refund_service import process_refund

            order.payment_status = "paid"
            session.add(order)
            result = process_refund(
                session, order, OrderStatus.PENDING,
                reason="Paid after the order was cancelled",
                idempotency_key=f"late-payment-{payment.id}", commit=False,
            )
            refund_failed = not result.get("processed", False)
        else:
            send_confirmation = order.payment_status != "paid"
            if order.status == OrderStatus.PENDING:
                order.status = OrderStatus.CONFIRMED
            order.payment_status = "paid"
            session.add(order)
        if send_confirmation:
            enqueue_order_email(session, order, "order_confirmation")
        session.commit()
        session.refresh(payment)
    except Exception:
        session.rollback()
        raise

    if refund_failed:
        raise HTTPException(503, "Late payment recorded; automatic refund needs retry")
    return payment


def record_payment_failure(session: Session, payment: Payment, *, cancel_order=False):
    """Ignore out-of-order failures for settled money; cancel only unpaid orders."""
    try:
        order, payment = _lock(session, payment)
        if (payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED)
                or order.payment_status == "paid"
                or order.payment_status.startswith("refund_")):
            return payment
        payment.status = PaymentStatus.FAILED
        session.add(payment)
        cancelled = False
        if cancel_order:
            from app.services.order_expiry import cancel_pending_online_order
            cancelled = cancel_pending_online_order(
                session, order, reason="Payment was cancelled or failed before it completed — order cancelled."
            )
        if not cancelled:
            session.commit()
        if cancelled:
            from app.services.order_expiry import notify_order_cancelled
            notify_order_cancelled(session, order)
        return payment
    except Exception:
        session.rollback()
        raise
