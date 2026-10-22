from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep,CurrentUser
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.repositories import order as order_repo
from app.schemas.order import (
    CancelOrderRequest,
    CancelOrderResponse,
    OrderRead,
    RefundInfo,
    RefundStatusResponse,
)
from app.services.email_outbox import enqueue_order_email
from app.services.refund_service import fetch_refund_status, process_refund, restore_stock
from app.services.shipping_status import shipment_stage_payload
from app.repositories import notification as notification_repo
from app.core.config import settings
from app.core.store_settings import get_store_settings
from app.core.region import format_money


def _refund_processing_days() -> int:
    return int(get_store_settings().refund_processing_days)


router = APIRouter(prefix="/orders", tags=["Orders"])


def _with_shipment_stage(order: Order) -> Order:
    """Attach the customer-facing fulfilment stage before serialisation.

    ``OrderRead`` is built with ``from_attributes``, so a plain attribute set
    here flows into the response. Deriving the stage server-side means the
    customer's tracking card can never contradict the status that triggered
    their notification email.

    ``shipment_stage`` is a response-only concern — it is not a column on the
    ``orders`` table — and SQLModel/Pydantic rejects unknown attribute
    assignment on a table model, hence ``object.__setattr__``.
    """
    object.__setattr__(
        order,
        "shipment_stage",
        shipment_stage_payload(
            has_awb=bool(order.awb_code),
            pickup_scheduled=bool(order.pickup_scheduled_date),
            shipment_status=order.shipment_status,
            order_status=order.status.value if hasattr(order.status, "value") else order.status,
        ),
    )
    return order


@router.get("", response_model=list[OrderRead])
def get_orders(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
):
    """Get all orders for current user"""
    orders = order_repo.get_orders_by_user(session, current_user.id, skip, limit)
    return [_with_shipment_stage(o) for o in orders]


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get specific order by ID"""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return _with_shipment_stage(order)


# =========================================================
# CANCELLATION & REFUND ENDPOINTS
# =========================================================

@router.post("/{order_id}/cancel", response_model=CancelOrderResponse)
def cancel_order(
    order_id: UUID,
    cancel_data: CancelOrderRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Cancel an order.

    - PENDING / CONFIRMED / PROCESSING orders can be cancelled.
    - Stock is restored for all items.
    - COD orders: cancelled, no refund.
    - Online paid orders: cancelled + Razorpay refund (minus restocking fee).
    """
    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # --- Validate cancellable status ---
    if order.status == OrderStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has already been cancelled",
        )
    if order.status == OrderStatus.REFUNDED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has already been refunded",
        )
    if order.status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order cannot be cancelled. Current status: {order.status.value}",
        )
    if not order.can_cancel:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order cannot be cancelled. Current status: {order.status.value}",
        )

    # Capture the status BEFORE we change it (drives restocking fee)
    status_at_cancellation = order.status

    # --- Update order to cancelled ---
    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = cancel_data.reason
    order.cancelled_at = datetime.now(timezone.utc)
    session.add(order)

    # --- Restore stock ---
    restore_stock(session, order)
    enqueue_order_email(session, order, "order_cancelled")

    # --- Refund logic ---
    refund_info: RefundInfo
    if order.payment_method == "cod":
        refund_info = RefundInfo(
            processed=False,
            amount=0,
            restocking_fee=0,
            fee_percentage=0,
            message="No refund needed — this is a Cash on Delivery order",
        )
        session.commit()
        session.refresh(order)
    elif order.payment_status == "paid":
        result = process_refund(
            session,
            order,
            status_at_cancellation,
            cancel_data.reason,
            requested_by=current_user.id,
        )
        refund_info = RefundInfo(
            processed=result["processed"],
            amount=result["amount"],
            restocking_fee=result["restocking_fee"],
            fee_percentage=Decimal(str(result["fee_percentage"])),
            refund_id=result.get("refund_id"),
            status=result.get("status"),
            message=result.get("message"),
        )
    else:
        order.payment_status = "cancelled"
        session.commit()
        session.refresh(order)
        refund_info = RefundInfo(
            processed=False,
            amount=0,
            restocking_fee=0,
            fee_percentage=0,
            message="Order cancelled before payment — no refund needed",
        )

    # --- Notify managers/admins about the cancellation (notifications feed) ---
    try:
        notification_repo.notify_admins_order_cancelled(session, order)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to create cancellation notifications: {str(e)}")

    return CancelOrderResponse(
        order_id=order.id,
        order_number=order.order_number,
        status=order.status.value,
        message="Order cancelled successfully",
        refund=refund_info,
    )


@router.get("/{order_id}/refund-status", response_model=RefundStatusResponse)
def get_refund_status(
    order_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Get the refund status for an order.

    Returns the stored refund details plus a live status lookup from the
    payment provider (Razorpay / dummy).
    """
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if not order.refund_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No refund found for this order",
        )

    # Live lookup from the order's own provider (not the global setting).
    live = fetch_refund_status(order, session)
    live_status = live.get("status", "unknown")

    # ---- Friendly message based on our stored phase + live provider state ----
    if order.payment_status == "refund_completed":
        message = f"Your refund of {format_money(order.refund_amount)} has been completed and credited to your account ✅"
    elif order.payment_status == "refund_failed" or live_status == "failed":
        message = "Refund failed. Please contact support for assistance."
    elif order.payment_status == "refund_initiated":
        message = (
            f"Your refund of {format_money(order.refund_amount)} is being processed. "
            f"It will be credited within {_refund_processing_days()} business days."
        )
    else:
        status_messages = {
            "processed": f"Refund of {format_money(order.refund_amount)} has been processed. It will reflect in your account within {_refund_processing_days()} business days.",
            "pending": "Refund is being processed. Please check back shortly.",
            "failed": "Refund failed. Please contact support for assistance.",
        }
        message = status_messages.get(live_status, f"Refund status: {live_status}")

    return RefundStatusResponse(
        order_id=order.id,
        order_number=order.order_number,
        refund_id=order.refund_id,
        refund_amount=order.refund_amount,
        restocking_fee=order.restocking_fee,
        fee_percentage=Decimal(str(order.restocking_fee_percentage)),
        payment_status=order.payment_status,
        status=live_status,
        message=message,
    )


@router.get("/number/{order_number}", response_model=OrderRead)
def get_order_by_number(
    order_number: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Get specific order by order number"""
    order = order_repo.get_order_by_number(session, order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return _with_shipment_stage(order)
