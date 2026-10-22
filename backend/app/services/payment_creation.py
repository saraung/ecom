"""Creation journal survives provider success followed by local commit failure."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.core.region import currency_code
from app.core.store_settings import get_store_settings
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.payment_creation import PaymentCreation
from app.repositories import payment as payment_repo
from app.schemas.payment import PaymentIntentResponse
from app.services.payment_service import get_payment_service_for_payment


def _eligible_order(session, order_id, user):
    order = session.execute(select(Order).where(Order.id == order_id).with_for_update()
                            .execution_options(populate_existing=True)).scalars().first()
    if order is None:
        raise HTTPException(404, "Order not found")
    if order.user_id != user.id:
        raise HTTPException(403, "Not authorized")
    if order.payment_method == "cod":
        raise HTTPException(400, "This is a Cash on Delivery order. Payment will be collected on delivery.")
    if order.status != OrderStatus.PENDING or order.payment_status != "pending":
        raise HTTPException(409, "This order is no longer awaiting payment")
    policy = get_store_settings(session, seed=False)
    placed = order.placed_at.replace(tzinfo=timezone.utc) if order.placed_at.tzinfo is None else order.placed_at
    if placed <= datetime.now(timezone.utc) - timedelta(minutes=policy.pending_order_expiry_minutes):
        raise HTTPException(409, "The payment window for this order has expired")
    payments = session.execute(select(Payment).where(Payment.order_id == order.id)
                              .order_by(Payment.created_at.desc(), Payment.id)
                              .execution_options(populate_existing=True)).scalars().all()
    if any(p.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED) for p in payments):
        raise HTTPException(409, "This order already has a captured payment")
    return order, payments


def _attempt(session, order):
    return session.execute(select(PaymentCreation).where(PaymentCreation.order_id == order.id)
                           .execution_options(populate_existing=True)).scalars().first()


def _legacy_response(payment, order):
    provider = getattr(payment.provider, "value", payment.provider)
    secret = payment.provider_payment_id
    if provider == "stripe":
        remote = get_payment_service_for_payment(payment).get_payment_intent(payment.provider_payment_id)
        if not remote or not remote.get("client_secret"):
            raise HTTPException(503, "Existing payment could not be recovered; retry later")
        secret = remote["client_secret"]
    elif provider == "dummy":
        secret += "_secret_dummy"
    return PaymentIntentResponse(client_secret=secret, payment_intent_id=payment.provider_payment_id,
                                 order_id=order.id, amount=payment.amount, currency=payment.currency,
                                 provider=provider, is_dummy=provider == "dummy")


def create_or_reuse_intent(session, request, user, service_factory):
    try:
        order, payments = _eligible_order(session, request.order_id, user)
        attempt = _attempt(session, order)
        if attempt is None and payments:
            # Preserve old gateway objects; do not mint another just because
            # pre-migration rows did not record their checkout response.
            payment = payments[0]
            if payment.amount != order.grand_total:
                raise HTTPException(409, "Existing payment amount differs from the order")
            return _legacy_response(payment, order)
        if attempt is not None and attempt.state == "ready":
            return PaymentIntentResponse.model_validate(attempt.response)
        if attempt is None:
            service = service_factory()
            provider = getattr(service, "provider_name", settings.PAYMENT_PROVIDER)
            attempt = PaymentCreation(order_id=order.id, provider=provider, currency=currency_code(),
                                      amount=order.grand_total, payment_method=request.payment_method)
            session.add(attempt)
            session.commit()  # Journal exists before any provider request.

        order, _ = _eligible_order(session, request.order_id, user)
        attempt = _attempt(session, order)
        if attempt.state == "ready":
            return PaymentIntentResponse.model_validate(attempt.response)
        may_create = attempt.state == "prepared"
        if may_create:
            attempt.state = "submitting"
            session.add(attempt)
            session.commit()  # A crash now is ambiguous, never a fresh attempt.
            order, _ = _eligible_order(session, request.order_id, user)
            attempt = _attempt(session, order)
            if attempt.state == "ready":
                return PaymentIntentResponse.model_validate(attempt.response)
        if order.grand_total != attempt.amount:
            raise HTTPException(409, "Order amount changed after payment creation began")
        service = get_payment_service_for_payment(SimpleNamespace(provider=attempt.provider))
        if getattr(service, "provider_name", None) != attempt.provider:
            raise HTTPException(503, "The recorded payment provider is unavailable")
        try:
            if may_create:
                result = service.create_payment_intent(order, attempt.payment_method,
                                                       idempotency_key=attempt.creation_key, currency=attempt.currency)
            else:
                result = service.recover_payment_creation(order, attempt)
        except Exception as exc:
            raise HTTPException(503, "Payment creation needs provider reconciliation; retry later") from exc
        if result is None:
            raise HTTPException(503, "Payment creation is awaiting provider reconciliation; retry later")
        response = PaymentIntentResponse(client_secret=result["client_secret"],
            payment_intent_id=result["payment_intent_id"], order_id=result["order_id"],
            amount=result["amount"], currency=result["currency"], provider=attempt.provider,
            is_dummy=attempt.provider == "dummy")
        if response.amount != attempt.amount or response.currency != attempt.currency or response.order_id != order.id:
            raise HTTPException(502, "Provider payment does not match the recorded attempt")
        payment_repo.create_payment(session, order.id, attempt.provider, response.payment_intent_id,
                                    response.amount, response.currency,
                                    payment_method=order.payment_method or attempt.payment_method, commit=False)
        attempt.response = response.model_dump(mode="json")
        attempt.state = "ready"
        session.add(attempt)
        session.commit()
        return response
    except Exception:
        session.rollback()
        raise
