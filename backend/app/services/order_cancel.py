# app/services/order_cancel.py
"""Shared admin order-cancellation (single source of truth).

Extracted verbatim from ``app/api/v1/admin/refunds.py:admin_cancel_order``
so the REST admin endpoint and the MCP cancellation tool execute identical
business logic: status guards, stock restoration, email, audit, transaction
handling, and the optional refund-now pipeline. No new behavior here.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlmodel import Session

from app.models.order import Order, OrderStatus
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import notification as notification_repo
from app.repositories import order as order_repo
from app.services import refund_service
from app.services.email_outbox import enqueue_order_email
from app.services.refund_service import restore_stock


def raise_if_provider_mismatch(result: dict, order: Order) -> None:
    """Map a provider/ledger mismatch to a structured 409.

    The frontend keys off ``code == "provider_mismatch"`` to offer record
    sync instead of another doomed retry. Plain failures keep flowing to
    the normal response shape.
    """
    state = result.get("provider_state")
    if not state:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "message": result.get(
                "message",
                "The payment provider disagrees with our refund records.",
            ),
            "code": "provider_mismatch",
            "order_id": str(order.id),
            "order_number": order.order_number,
            "provider": state.get("provider"),
            "provider_refunded": state.get("provider_refunded"),
            "provider_remaining": state.get("provider_remaining"),
            "recorded_refunded": state.get("recorded_refunded"),
        },
    )


def validate_cancellable(order: Order) -> None:
    """Raise HTTPException unless the order may be cancelled right now.

    Shared by the REST endpoint and the MCP tool so previews, executions,
    and admin clicks enforce identical state rules.
    """
    if order.status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is already {order.status.value}",
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


def cancel_order_as_admin(
    session: Session,
    *,
    order_id: UUID,
    actor: User,
    reason: str,
    refund_choice: str = "later",
    restock: bool = True,
    notify_customer: bool = True,
    idempotency_key: str | None = None,
    request: Request | None = None,
    commit: bool = True,
) -> dict:
    """Cancel an order from an admin context with an explicit money choice.

    - COD / unpaid orders: cancel + restock only (no money to move).
    - Paid online orders + refund_choice=now: cancel + restock + refund via
      the pipeline (executes within authority, else stages approval).
    - Paid online orders + refund_choice=later: cancel + restock, money
      stays captured, refundable balance left open and flagged.
    """
    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    validate_cancellable(order)

    paid_online = order.payment_method != "cod" and order.payment_status == "paid"
    if paid_online and refund_choice == "now":
        # Refuse before staging cancellation, restock or audit changes.
        refund_service.assert_refund_permission(session, actor)

    status_at_cancel = order.status
    order.status = OrderStatus.CANCELLED
    order.cancellation_reason = reason
    order.cancelled_at = datetime.now(timezone.utc)
    session.add(order)

    if restock:
        restore_stock(session, order)
    if notify_customer:
        enqueue_order_email(session, order, "order_cancelled")

    audit_repo.log(
        session,
        action="order.cancelled",
        entity="order",
        entity_id=order.id,
        actor_id=actor.id if actor else None,
        before={"status": status_at_cancel.value},
        after={"status": "cancelled", "reason": reason,
               "refund_choice": refund_choice},
        ip_address=audit_repo.client_ip(request) if request is not None else None,
    )

    refund_info: dict | None = None
    paid_online = (
        order.payment_method != "cod" and order.payment_status == "paid"
    )
    if paid_online and refund_choice == "now":
        result = refund_service.request_admin_refund(
            session,
            order,
            requested_by=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            status_at=status_at_cancel,
            notify_customer=notify_customer,
            commit=False,
        )
        refund_info = result
        raise_if_provider_mismatch(result, order)
        audit_repo.log(
            session,
            action="refund.approval_requested"
            if result.get("requires_approval") else "refund.executed",
            entity="refund",
            entity_id=result.get("refund_row_id") or order.id,
            actor_id=actor.id if actor else None,
            after={"amount": str(result.get("amount")),
                   "requires_approval": result.get("requires_approval")},
            ip_address=audit_repo.client_ip(request) if request is not None else None,
        )
    elif paid_online:
        refund_info = {
            "processed": False,
            "requires_approval": False,
            "message": (
                "Order cancelled without refund (refund later). "
                "The refundable balance is left open — follow up to avoid "
                "a chargeback on captured funds."
            ),
        }

    if commit:
        session.commit()
        session.refresh(order)

    # Customer notification (non-fatal).
    try:
        if notify_customer:
            notification_repo.notify_customer_status_changed(
                session, order, order.status.value
            )
            notification_repo.notify_admins_order_cancelled(session, order)
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to send admin-cancel notifications: {e}")

    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "status": order.status.value,
        "refund": refund_info,
    }
