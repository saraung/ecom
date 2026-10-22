from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from app.models.payment import Payment, PaymentStatus


def create_payment(
    session: Session,
    order_id: UUID,
    provider: str,
    provider_payment_id: str,
    amount: float,
    currency: str = "INR",
    metadata: dict = None,
    payment_method: str | None = None,
    *, commit: bool = True,
) -> Payment:
    """Create a new payment record"""
    payment = Payment(
        order_id=order_id,
        provider=provider,
        provider_payment_id=provider_payment_id,
        amount=amount,
        currency=currency,
        payment_metadata=metadata or {},
        payment_method=payment_method,
        status=PaymentStatus.PENDING,
    )
    session.add(payment)
    if commit:
        session.commit()
        session.refresh(payment)
    else:
        session.flush()
    return payment


def get_payment_by_id(session: Session, payment_id: UUID) -> Payment | None:
    """Get payment by ID"""
    return session.get(Payment, payment_id)


def get_payment_by_provider_id(
    session: Session, 
    provider_payment_id: str
) -> Payment | None:
    """Get payment by provider payment ID"""
    # 👇 Use execute() instead of exec()
    statement = select(Payment).where(
        Payment.provider_payment_id == provider_payment_id
    )
    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_payments_by_order(session: Session, order_id: UUID) -> list[Payment]:
    """Get all payments for an order"""
    statement = select(Payment).where(Payment.order_id == order_id)
    result = session.execute(statement)
    return result.scalars().all()


def update_payment_status(
    session: Session,
    payment: Payment,
    status: str,
    provider_payment_intent: str | None = None,
    payment_method: str | None = None,
    last_four: str | None = None,
) -> Payment:
    """Update payment status"""
    payment.status = status
    payment.updated_at = datetime.now(timezone.utc)
    
    if provider_payment_intent:
        payment.provider_payment_intent = provider_payment_intent
    
    if payment_method:
        payment.payment_method = payment_method
    
    if last_four:
        payment.last_four = last_four
    
    if status == "succeeded":
        payment.paid_at = datetime.now(timezone.utc)
    elif status == "refunded":
        payment.refunded_at = datetime.now(timezone.utc)
    
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


def mark_payment_succeeded(
    session: Session,
    provider_payment_id: str,
    provider_payment_intent: str | None = None,
    payment_method: str | None = None,
) -> Payment | None:
    """Mark payment as succeeded"""
    payment = get_payment_by_provider_id(session, provider_payment_id)
    if payment:
        return update_payment_status(
            session, 
            payment, 
            "succeeded",
            provider_payment_intent=provider_payment_intent,
            payment_method=payment_method,
        )
    return None


def mark_payment_failed(
    session: Session,
    provider_payment_id: str,
) -> Payment | None:
    """Mark payment as failed"""
    payment = get_payment_by_provider_id(session, provider_payment_id)
    if payment:
        return update_payment_status(session, payment, "failed")
    return None
