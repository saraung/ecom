import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep, CurrentUser
from app.models.user import User
from app.repositories import order as order_repo
from app.repositories import payment as payment_repo
from app.schemas.payment import (
    PaymentCreateRequest,
    PaymentRead,
    PaymentIntentResponse,
    PaymentConfirmRequest,
)
from app.services.payment_service import get_payment_service
from app.services import payment_service as provider_services
from app.services.payment_settlement import settle_payment, record_payment_failure
from app.models.payment import PaymentStatus
from app.services.payment_creation import create_or_reuse_intent
from app.services.email_service import email_service
from app.core.config import settings


router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-intent", response_model=PaymentIntentResponse)
def create_payment_intent(
    request: PaymentCreateRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Create payment intent.
    
    - Dummy mode: Always succeeds (for testing)
    - Real mode: Creates actual payment intent
    """
    return create_or_reuse_intent(session, request, current_user, get_payment_service)


@router.post("/confirm", response_model=PaymentRead)
def confirm_payment(
    request: PaymentConfirmRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Confirm payment.
    
    - Dummy mode: Auto-succeeds
    - Real mode: Calls payment provider
    """
    # Get payment
    payment = payment_repo.get_payment_by_provider_id(
        session, request.payment_intent_id
    )
    if not payment:
        raise HTTPException(404, "Payment not found")
    
    # Check order ownership
    order = order_repo.get_order_by_id(session, payment.order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    
    if order.user_id != current_user.id:
        raise HTTPException(403, "Not authorized")
    
    # 🚫 COD orders can't be confirmed online — admin collects cash on delivery
    if order.payment_method == "cod":
        raise HTTPException(
            400,
            "Cash on Delivery orders cannot be confirmed online. Payment is collected on delivery.",
        )
    
    if payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED):
        return settle_payment(session, payment)

    # Confirmation belongs to the provider recorded on this payment.
    payment_service = provider_services.get_payment_service_for_payment(payment)
    
    # Confirm payment
    result = payment_service.confirm_payment(request.payment_intent_id)
    
    if result["status"] == "succeeded":
        # A client callback is not authoritative about the charge identity.
        transaction_id = result.get("transaction_id")
        if not transaction_id and not result.get("is_dummy", True):
            resolver = getattr(payment_service, "get_payment_id_for_order", None)
            if callable(resolver):
                transaction_id = resolver(payment.provider_payment_id)
        transaction_id = transaction_id or result.get("transaction_id") or payment.provider_payment_id

        return settle_payment(session, payment, result.get("method"), transaction_id)
    elif result["status"] == "pending":
        raise HTTPException(409, "Payment is still pending")
    else:
        record_payment_failure(session, payment)
        raise HTTPException(400, "Payment failed")
