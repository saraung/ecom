from datetime import datetime, timezone
from decimal import Decimal
import hmac

from fastapi import APIRouter, Request, HTTPException
from sqlmodel import Session

from app.api.deps import SessionDep
from app.models.order import OrderStatus
from app.core.config import settings
from app.services.email_outbox import enqueue_order_email
from app.repositories import order as order_repo
from app.repositories import payment as payment_repo
from app.repositories import notification as notification_repo
from app.services.payment_service import get_payment_service
from app.services.payment_settlement import settle_payment, record_payment_failure
from app.models.order import Order
from sqlalchemy import select
from app.services.refund_service import process_refund, restore_stock
from app.services.order_expiry import cancel_pending_online_order, notify_order_cancelled
from app.services.shipping_status import (
    TERMINAL_ORDER_STATUSES,
    is_rto_delivered,
    map_shiprocket_status,
    normalize_location,
    normalize_status,
)


router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


def _handle_legacy_refund_webhook(
    session: Session,
    event_type: str,
    refund_entity: dict,
) -> None:
    """
    Handle Razorpay refund webhook events.

    - refund.processed -> payment_status = "refund_completed"
    - refund.failed    -> payment_status = "refund_failed"

    Finds the order by the refund ID stored on it during process_refund().
    """
    refund_id = (refund_entity or {}).get("id")
    if not refund_id:
        print(f"⚠️ {event_type} webhook received without a refund id — ignored")
        return

    order = order_repo.get_order_by_refund_id(session, refund_id)
    if not order:
        print(f"⚠️ {event_type} webhook: no order found for refund_id {refund_id}")
        return

    order = session.execute(
        select(Order).where(Order.id == order.id).with_for_update()
        .execution_options(populate_existing=True)
    ).scalars().one()
    if order.payment_status == "refund_completed":
        return  # Neither duplicate completion nor a late failure can regress it.

    if event_type == "refund.processed":
        # Only flip to completed if we're still waiting on it — never downgrade
        if order.payment_status != "refund_completed":
            order.payment_status = "refund_completed"
            # The order itself must be REFUNDED (guards + admin stats depend on it).
            # process_refund() sets this at initiation; this is a safety net for
            # orders created before that change / partial-refund edge cases.
            if order.status != OrderStatus.REFUNDED:
                print(f"ℹ️ Order {order.order_number} status was '{order.status.value}' — promoting to REFUNDED")
                order.status = OrderStatus.REFUNDED
            if not order.refunded_at:
                order.refunded_at = datetime.now(timezone.utc)
            session.add(order)

            # Keep the payment record timestamp in sync
            for payment in order.payments or []:
                if not payment.refunded_at:
                    payment.refunded_at = order.refunded_at
                    session.add(payment)

            enqueue_order_email(session, order, "refund_completed", event_id=refund_id)
            session.commit()
            session.refresh(order)
            print(f"✅ Refund COMPLETED for order {order.order_number} (webhook: refund.processed)")

        else:
            print(f"Order {order.order_number} already marked refund_completed — ignoring duplicate event")

    elif event_type == "refund.failed":
        order.payment_status = "refund_failed"
        session.add(order)
        enqueue_order_email(session, order, "refund_failed", event_id=refund_id)
        session.commit()
        session.refresh(order)
        print(f"❌ REFUND FAILED for order {order.order_number} (refund_id {refund_id}) — manual intervention needed")

        # TODO: alert admin (email / Slack / dashboard notification) here


def _handle_refund_webhook(session, event_type, refund_entity):
    from app.models.refund import Refund, RefundStatus
    from app.services.refund_service import apply_refund_state, enqueue_refund_email, REFUND_COMPLETED_STATUSES
    refund_id = (refund_entity or {}).get("id")
    if not refund_id:
        return
    ledger = session.execute(select(Refund).where(Refund.provider_refund_id == refund_id)).scalars().first()
    if ledger is None:
        return _handle_legacy_refund_webhook(session, event_type, refund_entity)
    try:
        order = order_repo.get_order_by_id(session, ledger.order_id, for_update=True)
        session.refresh(ledger, with_for_update=True)
        if ledger.provider_status in REFUND_COMPLETED_STATUSES:
            return
        if event_type == "refund.processed":
            if ledger.status != RefundStatus.EXECUTED:
                order.refund_amount += ledger.amount
            ledger.status, ledger.provider_status, ledger.error = RefundStatus.EXECUTED, "processed", None
            event = "refund_completed"
        elif event_type == "refund.failed":
            if ledger.provider_status == "failed":
                return
            if ledger.status == RefundStatus.EXECUTED:
                order.refund_amount = max(Decimal(0), order.refund_amount - ledger.amount)
            ledger.status, ledger.provider_status = RefundStatus.FAILED, "failed"
            ledger.error = "Provider reported refund failure"
            event = "refund_failed"
        else:
            return
        session.add_all([order, ledger])
        apply_refund_state(session, order, failed=event_type == "refund.failed")
        enqueue_refund_email(session, order, ledger, event)
        session.commit()
    except Exception:
        session.rollback()
        raise


def _settle_payment(session: Session, payment, instrument: str | None, provider_payment_id: str | None):
    """Compatibility entry point; callback and webhook use the same reducer."""
    return settle_payment(session, payment, instrument, provider_payment_id)


@router.post("/payment")
async def payment_webhook(
    request: Request,
    session: SessionDep,
):
    """
    Payment webhook — works for any provider configured via PAYMENT_PROVIDER.

    - URL:      https://<your-domain>/api/v1/webhooks/payment
    - Security: each provider signs the RAW body with its own signature and
                header; verification happens inside the provider service
                (Stripe-Signature for Stripe, X-Razorpay-Signature for
                Razorpay). Invalid/missing signatures are rejected with 400.
    - Events handled (normalized):
                  payment.succeeded   -> payment + order paid
                  refund.processed    -> refund state transition
                  refund.failed       -> refund state transition
    - All other events are acknowledged with 200 and ignored.
    """
    raw_body = (await request.body()).decode("utf-8", errors="replace")
    signature = request.headers.get("stripe-signature") or request.headers.get("x-razorpay-signature", "")

    payment_service = get_payment_service()

    try:
        event = payment_service.handle_webhook(raw_body, signature)
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {str(e)}")

    event_type = event.get("event_type", "unknown")

    # Bad signature / unparseable body -> 400 so the provider retries with a valid one
    if event_type in ("invalid_signature", "invalid"):
        raise HTTPException(400, "Invalid webhook signature")

    # ---------------- Payment succeeded ----------------
    if event_type == "payment.succeeded":
        payment_id = event.get("payment_id") or (event.get("data") or {}).get("payment_intent_id")
        if payment_id:
            payment = payment_repo.get_payment_by_provider_id(session, payment_id)
            if payment:
                _settle_payment(
                    session,
                    payment,
                    event.get("payment_method"),
                    event.get("transaction_id"),
                )

    elif event_type in ("refund.processed", "refund.failed"):
        refund_id = event.get("refund_id")
        if refund_id:
            _handle_refund_webhook(session, event_type, {"id": refund_id})

    # ---------------- Payment abandoned / failed (webhook reconciliation) ----
    elif event_type in ("payment.cancelled", "payment.failed"):
        payment_id = event.get("payment_id") or (event.get("data") or {}).get("payment_intent_id")
        if payment_id:
            payment = payment_repo.get_payment_by_provider_id(session, payment_id)
            if payment:
                record_payment_failure(session, payment, cancel_order=True)

    # Any other event — acknowledged, no action
    return {"status": "received", "event_type": event_type}



# =========================================================
# SHIPROCKET TRACKING WEBHOOK
# =========================================================

@router.post("/shiprocket")
async def shiprocket_tracking_webhook(
    request: Request,
    session: SessionDep,
):
    """
    Shiprocket webhook endpoint for real-time tracking events.

    Receives events when the package is picked up, in transit, out for delivery,
    delivered, or returned (RTO).

    The real body is wrapped in a top-level ``data`` key::

        {"data": {"awb": "...", "current_status": "PICKED UP",
                  "shipment_status": 7, "location": "...", ...}}

    Flat bodies are still accepted because the admin simulator and the existing
    tests post that shape. All status parsing/transition logic lives in
    ``services.shipping_status`` so this endpoint and the simulator cannot drift.
    """
    webhook_token = settings.SHIPROCKET_WEBHOOK_TOKEN
    if not webhook_token or not webhook_token.strip():
        raise HTTPException(503, "Shipping webhook authentication is not configured")
    header_token = request.headers.get("x-shiprocket-token", "")
    if not hmac.compare_digest(header_token.encode(), webhook_token.encode()):
        raise HTTPException(401, "Unauthorized webhook token")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")
    if not isinstance(payload, dict):
        raise HTTPException(400, "Webhook payload must be a JSON object")

    return process_tracking_event(session, payload)


def process_tracking_event(session: Session, payload: dict) -> dict:
    """Apply a Shiprocket tracking event to the matching order.

    Shared by the public webhook endpoint and the admin simulator, so both go
    through exactly the same parsing, mapping and persistence path. That is what
    makes the simulator trustworthy: it cannot pass while production breaks.

    Never raises on bad input — Shiprocket retries non-2xx responses and will
    eventually disable the endpoint, so unknown/absent data is reported as
    ``ignored`` rather than 500ing.
    """
    # Real payloads nest everything under "data". Fall back to the top level so
    # flat payloads (simulator, tests, manual curl) keep working.
    data = payload.get("data")
    if not isinstance(data, dict):
        data = payload

    awb = data.get("awb") or data.get("awb_code")
    if not awb:
        return {"status": "ignored", "reason": "No AWB present in payload"}
    awb = str(awb).strip()

    # Reverse tracking is a separate item-return lifecycle, never outbound RTO.
    from app.services.product_return import tracking_event as return_tracking_event
    returned = return_tracking_event(session, awb, data)
    if returned is not None:
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        return returned

    order = order_repo.get_order_by_awb(session, awb)
    if not order:
        return {"status": "ignored", "reason": f"No order found with AWB {awb}"}
    order = order_repo.get_order_by_id(session, order.id, for_update=True)

    # Prefer the human-readable current_status; fall back to the numeric code
    # (which normalize_status resolves via Shiprocket's status table). The old
    # code called .upper() on this value directly, which raised AttributeError
    # on the numeric form and 500'd the webhook.
    raw_status = data.get("current_status") or data.get("shipment_status")
    label = normalize_status(raw_status)
    target_status, shipment_status = map_shiprocket_status(raw_status)

    location = normalize_location(data.get("location")) or "Logistics Facility"
    activity = (
        data.get("activity")
        or data.get("current_status_notes")
        or f"Shipment status: {label or 'UNKNOWN'}"
    )
    # Prefer Shiprocket's own event timestamp so a replayed event keeps its
    # original place in the timeline.
    event_date = str(data.get("date") or "").strip() or datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")

    scan_entry = {
        "date": event_date,
        "location": location,
        "activity": activity,
        "status": label or "UNKNOWN",
    }

    # Idempotency: Shiprocket retries a webhook until it gets a 2xx, so the same
    # scan can arrive more than once. Only append when it is genuinely new.
    current_scans = (
        list(order.tracking_data) if isinstance(order.tracking_data, list) else []
    )
    is_duplicate = any(
        isinstance(s, dict)
        and s.get("status") == scan_entry["status"]
        and s.get("date") == scan_entry["date"]
        and s.get("location") == scan_entry["location"]
        for s in current_scans
    )
    if not is_duplicate:
        current_scans.append(scan_entry)
        order.tracking_data = current_scans

    # Guard against out-of-order / late scans moving a finished order backwards.
    # Without this, a retry of an old "IN TRANSIT" arriving after "DELIVERED"
    # would un-deliver the parcel and re-send the customer a shipping email.
    current_status = order.status
    if current_status in TERMINAL_ORDER_STATUSES and target_status not in (
        None,
        current_status,
    ):
        print(
            f"⚠️ Order {order.order_number}: ignoring '{label}' — already "
            f"terminal at '{current_status.value}'"
        )
        target_status = None

    status_changed = False
    if target_status is not None and target_status != current_status:
        order.status = target_status
        status_changed = True

        if target_status == OrderStatus.SHIPPED:
            if not order.shipped_at:
                order.shipped_at = datetime.now(timezone.utc)
            enqueue_order_email(session, order, "order_shipped")

        elif target_status == OrderStatus.DELIVERED:
            if not order.delivered_at:
                order.delivered_at = datetime.now(timezone.utc)
            enqueue_order_email(session, order, "order_delivered")

            # COD on delivery: when Shiprocket reports DELIVERED for a COD
            # order, treat the courier's collection as the customer's COD
            # payment and record it idempotently. Duplicate webhooks cannot
            # create a second Payment (raise 409 / ignored here).
            # Imported lazily to avoid a circular import (admin.cod imports the
            # admin package which imports orders, which imports this webhooks
            # module).
            if order.payment_method == "cod" and order.payment_status == "cod_pending":
                from app.api.v1.admin.cod import record_cod_collection

                try:
                    record_cod_collection(
                        session,
                        order,
                        actor_id=None,
                        collected_by_email="shiprocket-webhook",
                        ip_address=None,
                    )
                except HTTPException as exc:
                    if exc.status_code not in (400, 409):
                        raise
                    print(
                        f"⚠️ Order {order.order_number}: COD collection already "
                        f"recorded — ignoring duplicate DELIVERED webhook"
                    )

        elif target_status == OrderStatus.RTO:
            # Stock restoration is handled below by the label-based,
            # flag-guarded block (covers INITIATED-then-DELIVERED and
            # retries without double-restore).
            pass

    # RTO restock independent of status movement: a parcel handed back to
    # the seller restocks when the LABEL says RTO DELIVERED, even if the
    # order status already read RTO from an earlier INITIATED scan (in
    # which case nothing above runs). Flag-guarded so retried webhooks can
    # never double-restore; delivered orders never restock.
    # (This supersedes the old in-branch restore, which missed the
    # INITIATED-then-DELIVERED sequence and could double-fire with it.)
    if (
        is_rto_delivered(label or "")
        and current_status != OrderStatus.DELIVERED
        and not order.rto_stock_restored
    ):
        from app.models.product_return import ReturnRequest
        # A fully refunded delivered return may project Order.REFUNDED. Its
        # original outbound AWB still must not restock the entire purchase.
        has_customer_return = session.execute(select(ReturnRequest.id).where(ReturnRequest.order_id == order.id)).first()
        if not has_customer_return:
            restore_stock(session, order)
            order.rto_stock_restored = True
            session.add(order)

    # Always record the courier's own status (even for events we do not model,
    # like NOC) so the admin timeline reflects reality.
    if shipment_status != "UNKNOWN":
        order.shipment_status = shipment_status
    if not order.shipment_status:
        order.shipment_status = label or "UNKNOWN"

    session.add(order)
    session.commit()
    session.refresh(order)

    # Notify the customer only when the order status actually moved. Shiprocket
    # fires many scans per shipment ("Bag Added To Trip" etc.); notifying on each
    # would spam the customer with identical messages.
    if status_changed:
        try:
            notification_repo.notify_customer_status_changed(
                session, order, order.status.value
            )
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Failed to create shipping status notification: {e}")

    return {
        "status": "success",
        "order_id": str(order.id),
        "order_status": order.status.value,
        "shipment_status": order.shipment_status,
        "event_status": label or "UNKNOWN",
        "status_changed": status_changed,
        "duplicate": is_duplicate,
    }
