# app/services/refund_service.py
"""Refund business logic: fee calculation, stock restoration, Razorpay refunds."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
import hashlib

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session
from fastapi import HTTPException

from app.core.config import settings
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.product import ProductVariant
from app.models.refund import Refund, RefundStatus
from app.models.user import User
from app.repositories import payment as payment_repo
from app.repositories import rbac as rbac_repo
from app.repositories import refund as refund_repo
from app.services.payment_service import PaymentService, get_payment_service, get_payment_service_for_payment
from app.core.region import format_money
from app.services.email_outbox import enqueue_order_email, enqueue_email


def _refund_processing_days(policy=None) -> int:
    from app.core.store_settings import get_store_settings

    return int((policy or get_store_settings()).refund_processing_days)


# Restocking fee % keyed by the order status AT THE TIME of cancellation.
# Store policy (DB-backed, env fallback) — read live so admin edits apply
# without a restart.
def _restocking_fee(which: str, policy=None) -> float:
    from app.core.store_settings import get_store_settings

    return float(getattr(policy or get_store_settings(), f"restocking_fee_{which}"))


RESTOCKING_FEE_MAP = {
    OrderStatus.PENDING: lambda policy=None: _restocking_fee("pending", policy),
    OrderStatus.CONFIRMED: lambda policy=None: _restocking_fee("confirmed", policy),
    OrderStatus.PROCESSING: lambda policy=None: _restocking_fee("processing", policy),
}

# Provider refund-status values that mean "refund was accepted and is in flight"
# (Razorpay: processed/pending · Stripe: succeeded/processing/requires_action · dummy: processed)
REFUND_ACCEPTED_STATUSES = {
    "processed",
    "pending",
    "succeeded",
    "processing",
    "requires_action",
}

# Provider refund-status values that mean the money has arrived back
REFUND_COMPLETED_STATUSES = {"processed", "succeeded"}


def _money(value: Decimal) -> Decimal:
    """Round to 2 decimal places (currency)."""
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_refund(order: Order, status_at_cancellation: OrderStatus, *, session=None, policy=None) -> dict:
    """
    Calculate the refund amount and restocking fee for an order.

    refund_amount = grand_total - restocking_fee - already_refunded
    """
    if policy is None:
        from app.core.store_settings import get_store_settings
        from sqlalchemy.orm import object_session
        session = session or (object_session(order) if isinstance(order, Order) else None)
        policy = get_store_settings(session, seed=False)
    fee_getter = RESTOCKING_FEE_MAP.get(status_at_cancellation)
    fee_percentage = fee_getter(policy) if fee_getter else 0.0

    restocking_fee = _money(Decimal(str(fee_percentage)) / 100 * order.grand_total)
    already_refunded = order.refund_amount or Decimal(0)
    if already_refunded > 0 or getattr(order, "restocking_fee", 0):
        restocking_fee = getattr(order, "restocking_fee", restocking_fee) or Decimal(0)

    refund_amount = order.grand_total - restocking_fee - already_refunded
    refund_amount = max(_money(refund_amount), Decimal(0))

    return {
        "refund_amount": refund_amount,
        "restocking_fee": restocking_fee,
        "fee_percentage": fee_percentage,
        "already_refunded": already_refunded,
    }


def restore_stock(session: Session, order: Order) -> int:
    """Claim release once and increment stock atomically in caller's transaction."""
    from sqlalchemy import select, update
    from app.models.order import OrderItem
    try:
        # Status decisions happen under this same parent lock in all callers.
        session.execute(select(Order.id).where(Order.id == order.id).with_for_update()).one()
        claimed = session.execute(update(Order).where(
            Order.id == order.id, Order.stock_released.is_(False),
        ).values(stock_released=True).returning(Order.id)).first()
        session.expire(order, ["stock_released"])
        if claimed is None:
            return 0
        quantities = {}
        for item in session.execute(select(OrderItem).where(OrderItem.order_id == order.id)).scalars():
            quantities[item.variant_id] = quantities.get(item.variant_id, 0) + item.quantity
        restored = 0
        for variant_id in sorted(quantities, key=str):
            result = session.execute(update(ProductVariant).where(ProductVariant.id == variant_id)
                                     .values(stock=ProductVariant.stock + quantities[variant_id])
                                     .execution_options(synchronize_session=False))
            loaded = session.identity_map.get(session.identity_key(ProductVariant, variant_id))
            if loaded is not None:
                session.expire(loaded, ["stock"])
            restored += result.rowcount
        return restored
    except Exception:
        session.rollback()
        raise


def _get_refundable_payment(session: Session, order: Order) -> Payment | None:
    """Captured payment, including legacy partials marked wholly refunded."""
    from sqlalchemy import select
    return session.execute(select(Payment).where(
        Payment.order_id == order.id,
        Payment.status.in_([PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED]),
    ).order_by(Payment.created_at.desc()).execution_options(populate_existing=True)).scalars().first()


def apply_refund_state(session, order, *, failed=False):
    """Project reserved refund balance without terminating partial fulfillment.

    Accepted pending refunds reserve balance; failed rows release it. Payment
    REFUNDED means the entire captured charge, not a policy balance minus fees.
    The caller holds the order lock and owns the mutation/audit/mail commit.
    """
    from sqlalchemy import select
    session.flush()
    accepted = session.execute(select(Refund).where(
        Refund.order_id == order.id, Refund.status == RefundStatus.EXECUTED,
    )).scalars().all()
    full_policy = order.refund_amount > 0 and order.refund_amount + order.restocking_fee >= order.grand_total
    if full_policy:
        order.status = OrderStatus.REFUNDED
        pending = any(row.provider_status not in REFUND_COMPLETED_STATUSES for row in accepted)
        order.payment_status = "refund_initiated" if pending else "refund_completed"
    else:
        order.payment_status = "refund_failed" if failed and order.status == OrderStatus.REFUNDED else "paid"
    payment = _get_refundable_payment(session, order)
    if payment:
        full_charge = order.refund_amount >= payment.amount
        payment.status = PaymentStatus.REFUNDED if full_charge else PaymentStatus.SUCCEEDED
        payment.refunded_at = order.refunded_at if full_charge else None
        session.add(payment)
    session.add(order)

    # Linked product returns finish only when their own provider ledger finishes.
    from app.services.product_return import sync_order_returns
    sync_order_returns(session, order)


def enqueue_refund_email(session, order, ledger, event):
    """Render this refund's amount/ID, not the order's cumulative balance."""
    from types import SimpleNamespace
    view = SimpleNamespace(customer_details=order.customer_details, order_number=order.order_number,
                           placed_at=order.placed_at, refund_amount=ledger.amount,
                           grand_total=ledger.amount, refund_id=ledger.provider_refund_id)
    return enqueue_email(session, f"order:{order.id}:{event}:{ledger.provider_refund_id}",
                         f"send_{event}", view, order.user)


def _resolve_razorpay_payment_id(payment: Payment, service=None) -> str:
    """
    Resolve the actual charge/payment ID (pay_xxx / ch_xxx) needed for refunds.

    - provider_payment_intent holds pay_xxx/ch_xxx once the webhook settled it
    - otherwise fetch it from the payment's OWN provider via
      get_payment_id_for_order(order_xxx) — never the globally configured one
    - dummy mode: fall back to whatever is stored

    ``service`` may be passed in (already per-payment routed) to avoid building
    it twice; when omitted it is routed from ``payment.provider``.
    """
    if payment.provider_payment_intent:
        return payment.provider_payment_intent

    if service is None:
        try:
            service = get_payment_service_for_payment(payment)
        except ValueError:
            return payment.provider_payment_id
    resolver = getattr(service, "get_payment_id_for_order", None)
    if callable(resolver):
        try:
            resolved = resolver(payment.provider_payment_id)
        except Exception:
            resolved = None
        if resolved:
            return resolved

    # Dummy mode / last resort
    return payment.provider_payment_id


def process_refund(
    session, order, status_at_cancellation, reason=None, requested_by=None,
    approved_by=None, idempotency_key=None, amount=None, *, commit=True,
    notify_customer=True, policy=None, return_request_id=None, manual_transfer_reference=None,
):
    try:
        return _process_refund(session, order, status_at_cancellation, reason, requested_by,
                              approved_by, idempotency_key, amount, commit=commit,
                               notify_customer=notify_customer, policy=policy,
                               return_request_id=return_request_id, manual_transfer_reference=manual_transfer_reference)
    except Exception:
        session.rollback()
        raise


def _process_refund(
    session: Session,
    order: Order,
    status_at_cancellation: OrderStatus,
    reason: str | None = None,
    requested_by: UUID | None = None,
    approved_by: UUID | None = None,
    idempotency_key: str | None = None,
    amount: Decimal | None = None,
    *,
    commit: bool = True,
    notify_customer: bool = True,
    policy=None,
    return_request_id: UUID | None = None,
    manual_transfer_reference: str | None = None,
) -> dict:
    """
    Execute a refund for an order via the configured provider.

    Every execution is recorded in the ``refunds`` ledger keyed by
    ``idempotency_key`` (default ``refund-<order>-<status>``):

    - same key + EXECUTED row  -> replayed result, NO second PSP call;
    - same key + PENDING row    -> the pending approval is executed in place;
    - same key + FAILED row     -> a fresh attempt row is created;
    - concurrent duplicate insert -> loser replays the winner's row.

    ``amount`` caps the refund (partial refunds); None refunds the full
    remaining balance. Updates the order's refund fields and marks the
    payment record refunded. Returns a refund info dict for API responses.
    """
    # Customer/system refunds have no admin approver. Every admin execution
    # must retain current DB authorization even when a router is bypassed.
    if approved_by is not None:
        assert_refund_permission(session, session.get(User, approved_by))
    from sqlalchemy import select
    order = session.execute(select(Order).where(Order.id == order.id).with_for_update()
                            .execution_options(populate_existing=True)).scalars().one()
    key = idempotency_key or f"refund-{order.id}-{status_at_cancellation.value}"
    existing = refund_repo.get_by_idempotency_key(session, key)
    if existing is not None and existing.order_id != order.id:
        raise HTTPException(409, "Refund key belongs to a different order")
    if existing is not None and existing.return_request_id:
        if return_request_id and return_request_id != existing.return_request_id:
            raise HTTPException(409, "Refund key belongs to a different return")
        return_request_id = existing.return_request_id
        manual_transfer_reference = existing.manual_transfer_reference
    if return_request_id:
        if approved_by is None:
            raise HTTPException(403, "Return refunds require an authorized admin")
        actor = session.get(User, approved_by)
        limit = effective_refund_limit(session, actor)
        if limit is not None and amount is not None and _money(amount) > limit:
            raise HTTPException(403, "Return refund exceeds approval authority")
        if approved_by == order.user_id and order.placed_by_staff:
            raise HTTPException(403, "The order owner cannot approve this return refund")
        if existing and existing.status == RefundStatus.PENDING_APPROVAL and approved_by in {existing.requested_by, order.user_id}:
            raise HTTPException(403, "A different authorized admin must approve this return refund")
        from app.services.product_return import validate_refund
        validate_refund(session, order, return_request_id, amount, key=key,
                        manual_reference=manual_transfer_reference, require_requested=True)
        status_at_cancellation = OrderStatus.DELIVERED
    from app.core.store_settings import get_store_settings
    policy = policy or get_store_settings(session, seed=False)
    calc = calculate_refund(order, status_at_cancellation, policy=policy)
    if existing is not None and existing.status == RefundStatus.PENDING_APPROVAL:
        calc["restocking_fee"] = existing.restocking_fee
        calc["refund_amount"] = max(_money(order.grand_total - existing.restocking_fee - order.refund_amount), Decimal(0))
    remaining = calc["refund_amount"]
    if not return_request_id:
        from app.services.product_return import unexecuted_return_reserve
        remaining = max(remaining - unexecuted_return_reserve(session, order), Decimal(0))
    restocking_fee = calc["restocking_fee"]

    refund_amount = remaining if amount is None else min(_money(amount), remaining)

    base = {
        "processed": False,
        "amount": refund_amount,
        "restocking_fee": restocking_fee,
        "fee_percentage": calc["fee_percentage"],
        "refund_id": None,
        "status": None,
        "requires_approval": False,
        "duplicate": False,
    }

    now = datetime.now(timezone.utc)
    if existing is not None and existing.status == RefundStatus.EXECUTED:
        return {
            **base,
            "processed": True,
            "duplicate": True,
            "amount": existing.amount,
            "refund_id": existing.provider_refund_id,
            "status": existing.provider_status,
            "message": "Refund already processed for this request (idempotent replay)",
        }
    if refund_amount <= 0:
        return {**base, "message": "Nothing to refund (order already fully refunded)"}
    if existing is not None and existing.status == RefundStatus.PENDING_APPROVAL:
        ledger = existing
        ledger.amount = refund_amount
        # Keep the fee captured at request time (computed from the
        # pre-cancel status) — approval-time recomputation would zero it.
        restocking_fee = ledger.restocking_fee
        if approved_by is not None:
            ledger.approved_by = approved_by
    elif existing is not None:
        # FAILED / REJECTED rows are history — retry as a fresh attempt.
        key = f"{key}-retry-{existing.created_at.strftime('%Y%m%d%H%M%S')}"
        ledger = Refund(
            order_id=order.id,
            amount=refund_amount,
            restocking_fee=restocking_fee,
            idempotency_key=key,
            status=RefundStatus.EXECUTED,
            reason=reason,
            requested_by=requested_by,
            approved_by=approved_by,
        )
        session.add(ledger)
    else:
        ledger = Refund(
            order_id=order.id,
            amount=refund_amount,
            restocking_fee=restocking_fee,
            idempotency_key=key,
            status=RefundStatus.EXECUTED,
            reason=reason,
            requested_by=requested_by,
            approved_by=approved_by,
        )
        session.add(ledger)

    if return_request_id:
        ledger.return_request_id = return_request_id
        ledger.manual_transfer_reference = manual_transfer_reference
        session.add(ledger)

    try:
        # Savepoint (not a full rollback): the caller may already have staged
        # changes (e.g. order.status=CANCELLED) that must survive a lost
        # duplicate-key race.
        savepoint = session.begin_nested()
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        winner = refund_repo.get_by_idempotency_key(session, key)
        if winner is not None and winner.status == RefundStatus.EXECUTED:
            return {
                **base,
                "processed": True,
                "duplicate": True,
                "amount": winner.amount,
                "refund_id": winner.provider_refund_id,
                "status": winner.provider_status,
                "message": "Refund already processed for this request (idempotent replay)",
            }
        raise

    payment = _get_refundable_payment(session, order)
    if not payment:
        ledger.status = RefundStatus.FAILED
        ledger.error = "No successful payment found for this order"
        session.add(ledger)
        session.commit() if commit else session.flush()
        return {**base, "message": "No successful payment found for this order"}

    # Route to the gateway that captured THIS payment — not the global
    # setting (a Razorpay order_xxx sent to Stripe is the "No such
    # payment_intent" failure). COD has no online money: refuse with a
    # clear message instead of calling any PSP.
    manual_cod = return_request_id is not None and order.payment_method == "cod"
    try:
        service = None if manual_cod else get_payment_service_for_payment(payment)
    except ValueError as e:
        ledger.status = RefundStatus.FAILED
        ledger.error = str(e)
        session.add(ledger)
        session.commit() if commit else session.flush()
        return {**base, "message": str(e)}

    razorpay_payment_id = None if manual_cod else _resolve_razorpay_payment_id(payment, service)

    notes = {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "reason": reason or "Order cancelled",
            "refund_key": "rf-" + hashlib.sha256(key.encode()).hexdigest()[:32],
            "refund_request_key": key,
    }
    if manual_cod:
        # Attested manual repayment, not an online transfer. Only inspected,
        # linked returns can enter this branch; original COD cancellation stays intact.
        marker = hashlib.sha256(f"{order.id}:{manual_transfer_reference}".encode()).hexdigest()[:40]
        result = {"status": "processed", "refund_id": "cod-return-" + marker}
    elif isinstance(service, PaymentService):
        recorded_ids = set(session.execute(select(Refund.provider_refund_id).where(
            Refund.order_id == order.id, Refund.provider_refund_id.is_not(None))).scalars())
        result = service.create_refund_safely(razorpay_payment_id, float(refund_amount), notes, recorded_ids)
    else:
        # Test/extension adapters retain the existing provider interface.
        result = service.create_refund(razorpay_payment_id, amount=float(refund_amount), notes=notes)
    if result.get("status") == "unknown":
        raise HTTPException(503, "Refund outcome needs provider reconciliation; retry the same request")

    if result.get("status") in REFUND_ACCEPTED_STATUSES:
        order.refund_amount = (order.refund_amount or Decimal(0)) + refund_amount
        order.refund_id = result["refund_id"]
        order.refund_reason = reason
        order.restocking_fee = restocking_fee
        order.refunded_at = now

        session.add(order)

        ledger.status = RefundStatus.EXECUTED
        ledger.provider_refund_id = result["refund_id"]
        ledger.provider_status = result.get("status")
        ledger.decided_at = now
        session.add(ledger)
        apply_refund_state(session, order)

        if notify_customer:
            event = "refund_completed" if result.get("status") in REFUND_COMPLETED_STATUSES else "order_refunded"
            enqueue_refund_email(session, order, ledger, event)
        session.commit() if commit else session.flush()
        if commit:
            session.refresh(order)

        return {
            **base,
            "processed": True,
            "refund_id": result["refund_id"],
            "status": result.get("status"),
            "payment_status": order.payment_status,
            "refund_row_id": str(ledger.id),
            "message": (
                f"Refund of {format_money(refund_amount)} initiated successfully. "
                f"It will reflect in your account within "
                f"{_refund_processing_days(policy)} business days."
            ),
        }

    ledger.status = RefundStatus.FAILED
    ledger.provider_status = result.get("status")
    ledger.error = result.get("error", "unknown error")
    session.add(ledger)
    session.commit() if commit else session.flush()

    # Provider/ledger mismatch probe (failure path only — no happy-path
    # cost): money refunded OUTSIDE the app (e.g. gateway dashboard) leaves
    # our ledger stale, and every retry then fails the same way. If the
    # provider reports MORE refunded than we recorded, attach ground truth
    # so callers can offer reconciliation instead of another doomed retry.
    provider_state = _detect_provider_mismatch(
        service, razorpay_payment_id, order
    )
    if provider_state is not None:
        return {
            **base,
            "status": result.get("status"),
            "provider_state": provider_state,
            "message": (
                f"Our records show {format_money(order.refund_amount or 0)} refunded, but "
                f"{provider_state['provider']} reports "
                f"{format_money(provider_state['provider_refunded'])} already refunded "
                f"({format_money(provider_state['provider_remaining'])} left on the charge). "
                "Sync records to reconcile, then refund the remainder."
            ),
        }
    return {
        **base,
        "status": result.get("status"),
        "message": (
            f"Refund failed: {result.get('error', 'unknown error')}. "
            "The order was cancelled — please contact support for the refund."
        ),
    }


def _detect_provider_mismatch(service, provider_payment_id: str, order: Order) -> dict | None:
    """Compare provider-side refunded total against our ledger.

    Returns ground truth when the provider shows MORE refunded than we
    recorded (external refund), else None. Test doubles without the query
    method (getattr guard) simply skip the probe.
    """
    query = getattr(service, "get_charge_refund_state", None)
    if not callable(query):
        return None
    try:
        state = query(provider_payment_id)
    except Exception:
        return None
    if not state:
        return None
    try:
        provider_refunded = Decimal(str(state.get("refunded_total") or 0))
    except Exception:
        return None
    recorded = order.refund_amount or Decimal(0)
    if provider_refunded <= recorded:
        return None
    provider_name = (
        "Stripe" if str(provider_payment_id).startswith(("pi_", "ch_")) else "Razorpay"
    )
    remaining = Decimal(str(state.get("charge_total") or 0)) - provider_refunded
    return {
        "provider": provider_name,
        "provider_refunded": float(provider_refunded),
        "provider_remaining": float(max(remaining, Decimal(0))),
        "recorded_refunded": float(recorded),
        "refunds": state.get("refunds") or [],
    }


def fetch_refund_status(order: Order, session=None) -> dict:
    """Fetch live refund status from the payment provider.

    Routes via the order's own payment row when a session is available;
    falls back to the global provider for legacy callers (status endpoint
    without a payment lookup).
    """
    if session is not None:
        try:
            payment = _get_refundable_payment(session, order)
            if payment is not None:
                service = get_payment_service_for_payment(payment)
                from sqlalchemy import select
                rows = session.execute(select(Refund).where(
                    Refund.order_id == order.id, Refund.provider_refund_id.is_not(None),
                ).order_by(Refund.created_at.desc(), Refund.id)).scalars().all()
                if not rows:
                    return service.get_refund_status(order.refund_id)
                if rows[0].status == RefundStatus.FAILED:
                    return service.get_refund_status(rows[0].provider_refund_id)
                rows = [row for row in rows if row.status == RefundStatus.EXECUTED]
                statuses = [service.get_refund_status(row.provider_refund_id).get("status", "unknown") for row in rows]
                status = ("failed" if "failed" in statuses else "processed" if
                          all(value in REFUND_COMPLETED_STATUSES for value in statuses) else "pending")
                return {"status": status, "refund_id": order.refund_id}
        except ValueError:
            return {"status": "failed", "refund_id": order.refund_id,
                    "error": "Cash on Delivery orders have no online refund"}
        except Exception:
            return {"status": "unknown", "refund_id": order.refund_id}
    service = get_payment_service()
    return service.get_refund_status(order.refund_id)


def assert_refund_permission(session: Session, user: User | None) -> None:
    """Operation-level authorization, independent of legacy roles/UI guards."""
    if (user is None or not user.is_active
            or not rbac_repo.user_has_permission(session, user.id, "orders.refund")):
        raise HTTPException(403, "Refund operations require orders.refund permission")


def effective_refund_limit(session: Session, user: User) -> Decimal | None:
    """Highest single-refund amount the user may execute WITHOUT approval.

    None = unlimited (any role with a NULL limit, e.g. admin).
    """
    roles = [role for role in rbac_repo.get_user_roles(session, user.id)
             if "orders.refund" in rbac_repo.get_role_permission_keys(session, role.id)]
    limits = [r.max_refund_amount for r in roles if r.max_refund_amount is not None]
    if len(limits) < len(roles):
        return None
    return max(limits) if limits else Decimal(0)


def status_at_cancellation(session: Session, order: Order) -> OrderStatus:
    """Best-effort recovery of the status an order held when it was cancelled.

    The restocking fee is keyed on the status AT cancellation time, but a
    follow-up refund necessarily runs when ``order.status`` is already
    ``cancelled`` — which is not in ``RESTOCKING_FEE_MAP`` and would silently
    refund 100% of the total. The ``order.cancelled`` audit entry records the
    prior status, so read it back from there.

    Falls back to CONFIRMED (the 5% mid-tier) when no audit entry exists,
    which is the conservative choice: it never over-refunds a customer.
    """
    from sqlalchemy import select

    from app.models.admin_audit import AdminAuditLog

    row = session.execute(
        select(AdminAuditLog.before)
        .where(
            AdminAuditLog.entity == "order",
            AdminAuditLog.entity_id == str(order.id),
            AdminAuditLog.action == "order.cancelled",
        )
        .order_by(AdminAuditLog.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if isinstance(row, dict):
        raw = row.get("status")
        try:
            recovered = OrderStatus(raw)
        except ValueError:
            recovered = None
        # Only cancellable states are ever recorded as the prior status, so
        # this is guaranteed to have a fee attached.
        if recovered in RESTOCKING_FEE_MAP:
            return recovered

    return OrderStatus.CONFIRMED


def refund_authorization(
    session: Session, user: User, order: Order, amount: Decimal
) -> dict:
    """Decide whether an admin refund executes or needs a second admin.

    Requires approval when:
    - the order was placed by staff and the requester owns it (self-dealing);
    - the amount exceeds the requester's effective role limit.
    """
    assert_refund_permission(session, user)
    if order.user_id == user.id and getattr(order, "placed_by_staff", False):
        return {
            "requires_approval": True,
            "reason": "Order was placed by you — a different admin must approve",
        }
    limit = effective_refund_limit(session, user)
    if limit is not None and amount > limit:
        return {
            "requires_approval": True,
            "reason": (
                f"{format_money(amount)} exceeds your single-refund limit of {format_money(limit)} — "
                "a different admin must approve"
            ),
        }
    return {"requires_approval": False, "reason": None}


def request_admin_refund(
    session: Session,
    order: Order,
    requested_by: User,
    reason: str,
    amount: Decimal | None = None,
    idempotency_key: str | None = None,
    status_at: OrderStatus | None = None,
    *, notify_customer: bool = True,
    commit: bool = True,
    return_request_id: UUID | None = None,
    manual_transfer_reference: str | None = None,
) -> dict:
    """Admin refund entry point: execute within authority, else stage approval.

    Always returns a dict with ``requires_approval``. Approval rows are
    executed later via :func:`approve_refund` by a different admin.
    """
    assert_refund_permission(session, requested_by)
    from app.repositories.order import get_order_by_id
    order = get_order_by_id(session, order.id, for_update=True)
    basis = OrderStatus.DELIVERED if return_request_id else status_at or order.status
    key = idempotency_key or f"refund-{order.id}-{basis.value}"
    if return_request_id:
        from app.services.product_return import validate_refund
        validate_refund(session, order, return_request_id, amount, key=key,
                        manual_reference=manual_transfer_reference, require_requested=True)
    from app.core.store_settings import get_store_settings
    policy = get_store_settings(session, seed=False)
    calc = calculate_refund(order, basis, policy=policy)
    if not return_request_id:
        from app.services.product_return import unexecuted_return_reserve
        calc["refund_amount"] = max(calc["refund_amount"] - unexecuted_return_reserve(session, order), Decimal(0))
    target = calc["refund_amount"] if amount is None else min(_money(amount), calc["refund_amount"])
    if target <= 0:
        return {
            "processed": False,
            "requires_approval": False,
            "amount": target,
            "message": "Nothing to refund (order already fully refunded)",
        }

    gate = refund_authorization(session, requested_by, order, target)
    key = idempotency_key or f"refund-{order.id}-{basis.value}"

    if not gate["requires_approval"]:
        return process_refund(
            session,
            order,
            basis,
            reason=reason,
            requested_by=requested_by.id,
            approved_by=requested_by.id,
            idempotency_key=key,
            amount=target,
            notify_customer=notify_customer,
            commit=commit,
            policy=policy,
            return_request_id=return_request_id,
            manual_transfer_reference=manual_transfer_reference,
        )

    # Stage for second-admin approval — NO PSP call here.
    existing = refund_repo.get_by_idempotency_key(session, key)
    if existing is not None and existing.status == RefundStatus.PENDING_APPROVAL:
        ledger = existing
    elif existing is not None and existing.status == RefundStatus.EXECUTED:
        return {
            "processed": True,
            "requires_approval": False,
            "duplicate": True,
            "amount": existing.amount,
            "refund_id": existing.provider_refund_id,
            "message": "Refund already processed for this request (idempotent replay)",
        }
    else:
        if existing is not None:
            key = f"{key}-{_ledger_suffix()}"
        ledger = Refund(
            order_id=order.id,
            amount=target,
            restocking_fee=calc["restocking_fee"],
            idempotency_key=key,
            status=RefundStatus.PENDING_APPROVAL,
            reason=reason,
            requested_by=requested_by.id,
            return_request_id=return_request_id,
            manual_transfer_reference=manual_transfer_reference,
        )
        session.add(ledger)
        from app.repositories.notification import notify_approvers_refund_pending
        for approver in notify_approvers_refund_pending(session, order, ledger, requested_by):
            enqueue_email(session, f"refund:{ledger.id}:approval:{approver.id}",
                          "send_refund_approval_needed", approver.email,
                          approver.full_name or approver.username, order.order_number,
                          ledger.amount, requested_by.full_name or requested_by.email, ledger.reason)
        session.commit() if commit else session.flush()
        if commit:
            session.refresh(ledger)
    return {
        "processed": False,
        "requires_approval": True,
        "amount": target,
        "refund_row_id": str(ledger.id),
        "message": gate["reason"],
    }


def _ledger_suffix() -> str:
    """Short unique suffix for retry/duplicate ledger keys."""
    from uuid import uuid4

    return uuid4().hex[:8]


def get_attention_queue(session: Session, limit: int = 100) -> dict:
    """Cancelled paid-online orders holding captured money, no refund in flight.

    Shared by the REST attention route and MCP inspection: only cancelled
    orders qualify (a delivered order with nothing refunded is normal, not
    work to do); fee-retained fully-covered orders and orders with a
    pending approval are excluded. Read-only: no ledger rows, no PSP calls.
    """
    from sqlmodel import col, select

    candidates = session.exec(
        select(Order).where(
            Order.status == OrderStatus.CANCELLED,
            Order.payment_method != "cod",
            Order.payment_status == "paid",
        )
        .order_by(col(Order.placed_at).desc())
        .limit(limit * 2)  # over-fetch: some drop out below
    ).all()

    items = []
    for order in candidates:
        refunded = order.refund_amount or Decimal(0)
        # Policy-aware remainder: the restocking fee (keyed on the
        # pre-cancel status) is retained revenue, not owed money. Without
        # this, every fee-retained order would sit in the queue forever
        # with no valid action (any refund attempt answers "Nothing to
        # refund").
        policy = calculate_refund(
            order, status_at_cancellation(session, order)
        )
        remaining = policy["refund_amount"]
        if remaining <= 0:
            continue
        pending, _ = refund_repo.list_refunds(
            session, skip=0, limit=1, order_id=order.id,
            status=RefundStatus.PENDING_APPROVAL,
        )
        if pending:
            continue
        customer = order.customer_details
        items.append({
            "order_id": str(order.id),
            "order_number": order.order_number,
            "status": order.status.value,
            "customer_email": customer.email if customer else None,
            "customer_name": (
                customer.full_name or customer.username
            ) if customer else None,
            "grand_total": float(order.grand_total or 0),
            "refunded": float(refunded),
            "remaining": float(remaining),
            "cancelled_at": (
                order.cancelled_at.isoformat() if order.cancelled_at else None
            ),
            "cancellation_reason": order.cancellation_reason,
        })
        if len(items) >= limit:
            break
    return {"count": len(items), "orders": items}


def approve_refund(
    session: Session, ledger: Refund, approver: User, *, commit: bool = True
) -> dict:
    """Execute a pending approval. Guards (all enforced here, not just at
    the route, so no caller can skip them):
    - approver differs from requester AND order owner (four-eyes rule);
    - approver is themselves authorized for the amount — otherwise an
      under-limit manager could rubber-stamp any pending refund and the
      per-role limits would be theater.
    """
    assert_refund_permission(session, approver)
    from app.repositories.order import get_order_by_id
    order = get_order_by_id(session, ledger.order_id, for_update=True)
    session.refresh(ledger, with_for_update=True)
    if order is None:
        raise ValueError("Order for this refund no longer exists")
    if ledger.status != RefundStatus.PENDING_APPROVAL:
        raise ValueError(f"Refund is {ledger.status.value}, not pending approval")
    if approver.id == ledger.requested_by:
        raise ValueError("The requesting admin cannot approve their own refund")
    if approver.id == order.user_id:
        raise ValueError("The order owner cannot approve this refund")
    limit = effective_refund_limit(session, approver)
    if limit is not None and ledger.amount > limit:
        raise ValueError(
            f"This refund ({format_money(ledger.amount)}) exceeds your approval authority "
            f"of {format_money(limit)} — an admin must approve it"
        )

    return process_refund(
        session,
        order,
        order.status,
        reason=ledger.reason,
        requested_by=ledger.requested_by,
        approved_by=approver.id,
        idempotency_key=ledger.idempotency_key,
        amount=ledger.amount,
        commit=commit,
        return_request_id=ledger.return_request_id,
        manual_transfer_reference=ledger.manual_transfer_reference,
    )


def reject_refund(
    session: Session, ledger: Refund, approver: User, note: str | None = None, *, commit: bool = True
) -> Refund:
    """Reject a pending approval (no money moves)."""
    assert_refund_permission(session, approver)
    from app.repositories.order import get_order_by_id
    get_order_by_id(session, ledger.order_id, for_update=True)
    session.refresh(ledger, with_for_update=True)
    if ledger.status != RefundStatus.PENDING_APPROVAL:
        raise ValueError(f"Refund is {ledger.status.value}, not pending approval")
    if approver.id == ledger.requested_by:
        raise ValueError("The requesting admin cannot reject their own refund")
    ledger.status = RefundStatus.REJECTED
    ledger.approved_by = approver.id
    ledger.decided_at = datetime.now(timezone.utc)
    if note:
        ledger.error = note
    session.add(ledger)
    if ledger.return_request_id:
        from app.services.product_return import sync_order_returns
        sync_order_returns(session, session.get(Order, ledger.order_id))
    session.commit() if commit else session.flush()
    if commit:
        session.refresh(ledger)
    return ledger
