# app/api/v1/admin/refunds.py
"""Unified admin cancel + refund ledger + approvals + audit viewer.

Money-movement rule enforced here:
- Cancelling/crediting a paid order ALWAYS goes through the refund
  pipeline (ledger row + PSP call), never a bare status flip.
- Above-limit or self-order refunds stage as pending_approval for a
  DIFFERENT admin instead of executing.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import SessionDep, require_perm
from app.models.order import Order, OrderStatus
from app.models.refund import Refund, RefundStatus
from app.models.user import User
from app.repositories import order as order_repo
from app.repositories import rbac as rbac_repo
from app.repositories import refund as refund_repo
from app.repositories import audit as audit_repo
from app.repositories import user as user_repo
from app.core.config import settings
from app.schemas.order import OrderRead
from app.schemas.refund import (
    AdminCancelRequest,
    AdminRefundRequest,
    RefundDecisionResponse,
    RefundListResponse,
    RefundRead,
    RefundRejectRequest,
)
from app.services import refund_service
from app.services import order_cancel as order_cancel_service
from app.services.payment_service import get_payment_service
from app.services.email_outbox import enqueue_order_email
from app.repositories import notification as notification_repo


router = APIRouter(tags=["Admin Refunds"])


def _ip(request: Request | None) -> str | None:
    """Client IP for the audit trail (honors X-Forwarded-For).

    Delegates to the audit repository so every admin router records the
    address the same way — behind the panel's proxy, ``request.client``
    is the ingress, not the admin who clicked.
    """
    return audit_repo.client_ip(request)


def _audit(
    session: SessionDep,
    request: Request | None,
    action: str,
    entity: str,
    entity_id,
    actor: User | None,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    audit_repo.log(
        session,
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_id=actor.id if actor else None,
        before=before,
        after=after,
        ip_address=_ip(request),
    )


def _refund_read(
    session: SessionDep, ledger
) -> RefundRead:
    order = session.get(Order, ledger.order_id)
    requester = (
        session.get(User, ledger.requested_by)
        if ledger.requested_by
        else None
    )
    return RefundRead(
        id=ledger.id,
        order_id=ledger.order_id,
        return_request_id=ledger.return_request_id,
        manual_transfer_reference=ledger.manual_transfer_reference,
        order_number=order.order_number if order else None,
        amount=ledger.amount,
        restocking_fee=ledger.restocking_fee,
        status=ledger.status.value,
        reason=ledger.reason,
        requested_by=ledger.requested_by,
        requester_email=requester.email if requester else None,
        approved_by=ledger.approved_by,
        provider_refund_id=ledger.provider_refund_id,
        provider_status=ledger.provider_status,
        error=ledger.error,
        created_at=ledger.created_at,
        decided_at=ledger.decided_at,
    )


# ============ REFUND LEDGER ============

@router.get("/admin/refunds/my-authority", response_model=dict)
def my_refund_authority(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.refund")),
):
    """The caller's own refund authority (drives proactive UI gating).

    Returns ``{"max_refund_amount": str|null, "unlimited": bool}``.
    The server re-checks on every approve — this is display-only.
    """
    limit = refund_service.effective_refund_limit(session, current_user)
    return {
        "max_refund_amount": str(limit) if limit is not None else None,
        "unlimited": limit is None,
    }


@router.get("/admin/refunds/attention", response_model=dict)
def refunds_attention(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.refund")),
    limit: int = Query(default=100, ge=1, le=200),
):
    """Action queue: cancelled paid-online orders holding captured money
    with no refund in flight.

    Only cancelled orders qualify: a delivered order with nothing refunded
    is the normal state of the world, not work to do — listing every
    delivered order would bury the real follow-ups. Delivered returns still
    have a money path (Issue Refund on the order), just not a queue entry.
    Fully refunded orders, COD/unpaid orders, and orders with a pending
    approval are excluded.
    """
    return refund_service.get_attention_queue(session, limit=limit)


@router.get("/admin/refunds", response_model=RefundListResponse)
def list_refunds(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.refund")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None),
    order_id: UUID | None = Query(default=None),
):
    """List refund ledger rows (requires orders.refund permission)."""
    from app.models.refund import RefundStatus

    status_enum = None
    if status_filter:
        try:
            status_enum = RefundStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown refund status: {status_filter}",
            )
    skip = (page - 1) * limit
    rows, total = refund_repo.list_refunds(
        session, skip=skip, limit=limit, status=status_enum, order_id=order_id
    )
    return RefundListResponse(
        refunds=[_refund_read(session, r) for r in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if limit else 1,
    )


@router.post("/admin/refunds/{refund_id}/approve", response_model=RefundDecisionResponse)
def approve_refund(
    refund_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.refund")),
):
    """Approve + execute a pending refund (approver must differ)."""
    ledger = refund_repo.get_by_id(session, refund_id)
    if not ledger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found"
        )
    try:
        result = refund_service.approve_refund(session, ledger, current_user, commit=False)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    order = session.get(Order, ledger.order_id)
    _audit(
        session, request, "refund.approved", "refund", ledger.id,
        current_user,
        before={"status": "pending_approval"},
        after={"status": "executed", "amount": str(result.get("amount")),
               "refund_id": result.get("refund_id")},
    )
    session.commit()
    # Customer notification (non-fatal).
    try:
        if order is not None:
            notification_repo.notify_customer_status_changed(
                session, order, order.status.value
            )
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to send refund-approval notifications: {e}")
    return RefundDecisionResponse(
        processed=bool(result.get("processed")),
        requires_approval=False,
        amount=result.get("amount"),
        refund_row_id=str(ledger.id),
        refund_id=result.get("refund_id"),
        message=result.get("message", "Refund executed"),
    )


@router.post("/admin/refunds/{refund_id}/reject", response_model=RefundRead)
def reject_refund(
    refund_id: UUID,
    data: RefundRejectRequest,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.refund")),
):
    """Reject a pending refund (no money moves)."""
    ledger = refund_repo.get_by_id(session, refund_id)
    if not ledger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Refund not found"
        )
    try:
        ledger = refund_service.reject_refund(
            session, ledger, current_user, note=data.note, commit=False
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    _audit(
        session, request, "refund.rejected", "refund", ledger.id,
        current_user,
        before={"status": "pending_approval"},
        after={"status": "rejected", "note": data.note},
    )
    session.commit()
    return _refund_read(session, ledger)


def _raise_if_provider_mismatch(result: dict, order: Order) -> None:
    """Map a provider/ledger mismatch to a structured 409.

    The frontend keys off ``code == "provider_mismatch"`` to offer record
    sync instead of another doomed retry. Plain failures keep flowing to
    the normal response shape.
    """
    order_cancel_service.raise_if_provider_mismatch(result, order)


# ============ FOLLOW-UP REFUND (CANCELLED ORDER) ============

@router.post("/admin/orders/{order_id}/refund", response_model=RefundDecisionResponse)
def refund_cancelled_order(
    order_id: UUID,
    data: AdminRefundRequest,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.refund")),
):
    """Refund without cancelling: ALREADY-cancelled follow-ups AND delivered returns — the "refund later" follow-up.

    Cancelling with ``refund_choice="later"`` deliberately moves no money and
    writes no ledger row, so the captured balance has to be released by a
    second, explicit step. This is that step, and it is the ONLY way to move
    money on an order that is already cancelled.

    Money-movement rules are identical to the cancel-time path because it
    delegates to the same ``request_admin_refund`` gate: within the actor's
    per-role limit it executes, above it (or on a self-order) it stages as
    pending_approval for a different admin, and no PSP call happens until
    that second admin approves.
    """
    from app.models.refund import RefundStatus

    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    if order.status == OrderStatus.REFUNDED and order.payment_status != "refund_failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has already been refunded",
        )
    if order.status not in (OrderStatus.CANCELLED, OrderStatus.DELIVERED, OrderStatus.REFUNDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only cancelled or delivered orders can be refunded here. "
                f"This order is {order.status.value} — cancel it first, choosing "
                "'refund now' if the money should move at the same time."
            ),
        )
    if order.payment_method == "cod":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cash on Delivery orders have no captured payment to refund",
        )
    if order.payment_status not in ("paid", "refund_failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Nothing to refund — this order's payment status is "
                f"'{order.payment_status}', not 'paid'"
            ),
        )

    # Reject if a refund is already awaiting approval, so a second click
    # cannot open a parallel request. An already-EXECUTED refund is handled
    # idempotently further down by calculate_refund (remaining balance 0).
    in_flight, _ = refund_repo.list_refunds(
        session, skip=0, limit=1, order_id=order.id,
        status=RefundStatus.PENDING_APPROVAL,
    )
    if in_flight:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A refund for this order is already awaiting approval. "
                "Review it on the Refunds page instead of starting another."
            ),
        )

    basis = refund_service.status_at_cancellation(session, order) if order.cancelled_at or order.status == OrderStatus.CANCELLED else order.status
    result = refund_service.request_admin_refund(
        session,
        order,
        requested_by=current_user,
        reason=data.reason,
        amount=data.amount,
        idempotency_key=data.idempotency_key,
        status_at=basis,
        notify_customer=data.notify_customer,
        commit=False,
    )
    _raise_if_provider_mismatch(result, order)
    _audit(
        session, request,
        "refund.approval_requested"
        if result.get("requires_approval") else "refund.executed",
        "refund", result.get("refund_row_id") or order.id,
        current_user,
        after={
            "order_id": str(order.id),
            "order_number": order.order_number,
            "amount": str(result.get("amount")),
            "status_at_cancellation": basis.value,
            "requires_approval": result.get("requires_approval"),
            "follow_up": True,
        },
    )
    session.commit()
    session.refresh(order)

    # Customer notification (non-fatal).
    try:
        if data.notify_customer and result.get("processed"):
            notification_repo.notify_customer_status_changed(
                session, order, order.status.value
            )
            session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to send follow-up refund notifications: {e}")

    return RefundDecisionResponse(
        processed=bool(result.get("processed")),
        requires_approval=bool(result.get("requires_approval")),
        amount=result.get("amount"),
        refund_row_id=result.get("refund_row_id"),
        refund_id=result.get("refund_id"),
        message=result.get("message", "Refund processed"),
    )


# ============ RECONCILE WITH PROVIDER ============

@router.post("/admin/orders/{order_id}/reconcile-refund", response_model=dict)
def reconcile_order_refunds(
    order_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.refund")),
):
    try:
        return _reconcile_order_refunds(order_id, session, request, current_user)
    except Exception:
        session.rollback()
        raise


def _reconcile_order_refunds(order_id, session, request, current_user):
    """Sync our ledger with provider-side truth (requires orders.refund).

    Pulls the charge's actual refunds from Stripe/Razorpay and records any
    that bypassed this app (e.g. gateway-dashboard refunds) as EXECUTED
    ledger rows, then re-derives the order's refunded total. Idempotent —
    re-running changes nothing. This is the fix path when a refund fails
    with "greater than unrefunded amount": sync first, then refund the
    remainder (if any).
    """
    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    payment = refund_service._get_refundable_payment(session, order)
    if not payment:
        # Fall back to any payment on the order (e.g. already marked refunded).
        payments = payment_repo.get_payments_by_order(session, order.id)
        payment = payments[0] if payments else None
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No payment found for this order",
        )

    try:
        service = refund_service.get_payment_service_for_payment(payment)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    provider_payment_id = refund_service._resolve_razorpay_payment_id(
        payment, service
    )
    query = getattr(service, "get_charge_refund_state", None)
    if not callable(query):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Provider refund lookup is not available",
        )
    state = query(provider_payment_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the payment provider — try again",
        )

    synced = 0
    for pref in state.get("refunds") or []:
        provider_status = str(pref.get("status") or "").lower()
        accepted = provider_status in refund_service.REFUND_ACCEPTED_STATUSES
        if accepted and not pref.get("id"):
            raise HTTPException(502, "Provider refund is missing its stable identity")
        if not accepted and provider_status not in ("failed", "canceled", "cancelled"):
            continue
        existing = None
        if pref.get("id"):
            existing = session.execute(
                select(Refund).where(Refund.provider_refund_id == pref.get("id"))
            ).scalars().first()
        if existing is not None:
            if existing.order_id != order.id or existing.amount != Decimal(str(pref.get("amount") or 0)):
                raise HTTPException(409, "Provider refund identity/amount disagrees with the ledger")
            if existing.provider_status in refund_service.REFUND_COMPLETED_STATUSES:
                continue
            target = RefundStatus.EXECUTED if accepted else RefundStatus.FAILED
            if existing.provider_status != provider_status or existing.status != target:
                existing.provider_status, existing.status = provider_status, target
                existing.error = None if accepted else "Provider reported refund failure"
                session.add(existing)
                synced += 1
            continue
        if not accepted:
            continue
        session.add(Refund(
            order_id=order.id,
            amount=Decimal(str(pref.get("amount") or 0)),
            restocking_fee=Decimal(0),
            idempotency_key=f"reconcile-{pref.get('id') or uuid4().hex}",
            status=RefundStatus.EXECUTED,
            reason="Accepted outside the app — reconciled from provider",
            requested_by=None,
            approved_by=None,
            provider_refund_id=pref.get("id"),
            provider_status=provider_status,
            decided_at=datetime.now(timezone.utc),
        ))
        synced += 1

    # Re-derive the order total from the full EXECUTED ledger (self-consistent).
    total = session.execute(
        select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.order_id == order.id,
            Refund.status == RefundStatus.EXECUTED,
        )
    ).scalar_one()
    if not order.refund_amount:
        basis = refund_service.status_at_cancellation(session, order) if order.status == OrderStatus.CANCELLED else order.status
        order.restocking_fee = refund_service.calculate_refund(order, basis, session=session)["restocking_fee"]
    released_balance = total < order.refund_amount
    order.refund_amount = total
    if total:
        order.refunded_at = order.refunded_at or datetime.now(timezone.utc)
    refund_service.apply_refund_state(session, order, failed=released_balance)
    session.add(order)
    _audit(
        session, request, "refund.reconciled", "order", order.id,
        current_user,
        after={"synced_rows": synced,
               "provider_refunded": state.get("refunded_total"),
               "recorded_refunded": float(total or 0)},
    )
    session.commit()
    session.refresh(order)

    remaining = (order.grand_total or Decimal(0)) - (total or Decimal(0))
    return {
        "synced_rows": synced,
        "provider_refunded": state.get("refunded_total"),
        "recorded_refunded": float(total or 0),
        "remaining": float(max(remaining, Decimal(0))),
        "order_status": order.status.value,
    }


# ============ UNIFIED ADMIN CANCEL ============

@router.post("/admin/orders/{order_id}/cancel", response_model=dict)
def admin_cancel_order(
    order_id: UUID,
    data: AdminCancelRequest,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.update")),
):
    """Cancel an order from the admin panel with an explicit money choice.

    - COD / unpaid orders: cancel + restock only (no money to move).
    - Paid online orders + refund_choice=now: cancel + restock + refund via
      the pipeline (executes within authority, else stages approval).
    - Paid online orders + refund_choice=later: cancel + restock, money
      stays captured, refundable balance left open and flagged.
    """
    return order_cancel_service.cancel_order_as_admin(
        session,
        order_id=order_id,
        actor=current_user,
        reason=data.reason,
        refund_choice=data.refund_choice,
        restock=data.restock,
        notify_customer=data.notify_customer,
        idempotency_key=data.idempotency_key,
        request=request,
        commit=True,
    )
