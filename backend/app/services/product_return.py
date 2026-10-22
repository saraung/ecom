"""Order-locked quantity reservations and explicit delivered-return transitions.

Mutations stage data/events/audit; routers own commit/rollback. Refunds delegate
to the existing authority, ledger and provider-recovery pipeline.
"""
import hashlib
import json
from datetime import timedelta, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.config import settings
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import PaymentProvider
from app.models.product_return import (
    REASON_LABELS, ReturnEvidence, ReturnEvent, ReturnItem, ReturnReason, ReturnRequest, ReturnStatus, utcnow,
)
from app.models.refund import Refund, RefundStatus
from app.models.user import User
from app.repositories import audit, order as order_repo, rbac
from app.services import refund_service
from app.services.cloudinary_service import upload_image
from app.services.shipping_status import map_shiprocket_status, normalize_location, normalize_status

RELEASED = (ReturnStatus.REJECTED, ReturnStatus.CANCELLED)
TERMINAL = (*RELEASED, ReturnStatus.REFUNDED)


def money(value):
    return Decimal(value).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)


def require_permission(session, actor, *keys):
    if actor is None or not actor.is_active or any(not rbac.user_has_permission(session, actor.id, key) for key in keys):
        raise HTTPException(403, "Insufficient return permissions")


def owned_order(session, order_id, actor, *, lock=False):
    order = order_repo.get_order_by_id(session, order_id, for_update=lock)
    if order is None or order.user_id != actor.id:
        raise HTTPException(404, "Order not found")
    return order


def get_request(session, return_id, *, owner=None, lock=False):
    row = session.get(ReturnRequest, return_id)
    if row is None or (owner is not None and row.user_id != owner.id):
        raise HTTPException(404, "Return not found")
    if lock:
        order_repo.get_order_by_id(session, row.order_id, for_update=True)
        row = session.execute(select(ReturnRequest).where(ReturnRequest.id == return_id).with_for_update()
                              .execution_options(populate_existing=True)).scalar_one()
    return row


def latest_refund(session, row):
    return session.execute(select(Refund).where(Refund.return_request_id == row.id)
                           .order_by(Refund.created_at.desc(), Refund.id.desc())).scalars().first()


def policy():
    if not set(settings.RETURN_REQUIRED_PHOTO_REASONS) <= set(REASON_LABELS):
        raise HTTPException(503, "Return evidence policy is invalid")
    try:
        excluded = {UUID(value) for value in settings.RETURN_EXCLUDED_VARIANT_IDS}
    except ValueError:
        raise HTTPException(503, "Return product eligibility policy is invalid")
    return {"enabled": settings.RETURNS_ENABLED, "window_days": settings.RETURN_WINDOW_DAYS,
            "fee_percent": settings.RETURN_FEE_PERCENT, "required_photo_reasons": settings.RETURN_REQUIRED_PHOTO_REASONS,
            "max_images": settings.RETURN_MAX_IMAGES, "max_image_bytes": settings.RETURN_IMAGE_MAX_BYTES,
            "excluded": excluded}


def merchandise_cents(order, items):
    """Largest-remainder allocation of immutable net merchandise to purchased lines."""
    total = sum((item.line_total for item in items), Decimal(0))
    pool = min(max(order.subtotal - order.discount_total + order.tax_total, Decimal(0)),
               max(order.grand_total - order.shipping_total - order.cod_fee, Decimal(0)))
    cents = int(money(pool) * 100)
    if total <= 0:
        return {item.id: 0 for item in items}
    exact = {item.id: Decimal(cents) * item.line_total / total for item in items}
    result = {key: int(value.to_integral_value(rounding=ROUND_DOWN)) for key, value in exact.items()}
    for key in sorted(exact, key=lambda key: (-(exact[key] - result[key]), str(key)))[:cents - sum(result.values())]:
        result[key] += 1
    return result


def reservations(session, order_id):
    rows = session.execute(select(ReturnItem.order_item_id, ReturnItem.quantity, ReturnItem.amount)
        .join(ReturnRequest, ReturnItem.return_id == ReturnRequest.id)
        .where(ReturnRequest.order_id == order_id, ReturnRequest.status.notin_(RELEASED))).all()
    result = {}
    for item_id, quantity, amount in rows:
        count, reserved = result.get(item_id, (0, Decimal(0)))
        result[item_id] = (count + quantity, reserved + amount)
    return result


def unexecuted_return_reserve(session, order):
    reserved = Decimal(0)
    for row in session.execute(select(ReturnRequest).where(
            ReturnRequest.order_id == order.id, ReturnRequest.status.notin_(TERMINAL))).scalars():
        ledger = latest_refund(session, row)
        if not ledger or ledger.status != RefundStatus.EXECUTED:
            reserved += row.refund_amount
    return reserved


def available_money(session, order):
    payment = refund_service._get_refundable_payment(session, order)
    remaining = max(min(order.grand_total - order.restocking_fee, payment.amount if payment else Decimal(0))
                    - order.refund_amount - unexecuted_return_reserve(session, order), Decimal(0))
    remaining -= session.execute(select(func.coalesce(func.sum(Refund.amount), 0)).where(
        Refund.order_id == order.id, Refund.return_request_id.is_(None),
        Refund.status == RefundStatus.PENDING_APPROVAL)).scalar_one()
    return max(money(remaining), Decimal(0))


def eligibility(session, order, actor):
    if order.user_id != actor.id:
        raise HTTPException(404, "Order not found")
    config = policy()
    payment = refund_service._get_refundable_payment(session, order)
    reason = None
    if not config["enabled"]:
        reason = "Product returns are currently disabled"
    elif order.cancelled_at or not (order.status == OrderStatus.DELIVERED or
            order.status == OrderStatus.REFUNDED and order.delivered_at is not None):
        reason = "Only delivered orders are eligible for product returns"
    elif order.payment_status not in {"paid", "refund_failed", "refund_initiated", "refund_completed"}:
        reason = "The order payment has not been collected"
    elif payment is None:
        reason = "No collected payment is available for this order"
    elif (order.payment_method == "cod") != (payment.provider == PaymentProvider.COD):
        reason = "The collected payment does not match this order's payment method"
    elif config["window_days"] is not None:
        delivered = order.delivered_at
        if delivered is None:
            reason = "A delivery date is required by the configured return policy"
        else:
            delivered = delivered.replace(tzinfo=timezone.utc) if delivered.tzinfo is None else delivered
            if utcnow() > delivered + timedelta(days=config["window_days"]):
                reason = "The configured return window has ended"
    items = session.execute(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)).scalars().all()
    pools, used = merchandise_cents(order, items), reservations(session, order.id)
    funds = available_money(session, order)
    if reason is None and funds <= 0:
        reason = "No unreserved refundable balance remains"
    result = []
    for item in items:
        count, value = used.get(item.id, (0, Decimal(0)))
        qty = max(item.quantity - count, 0)
        item_reason = reason or ("This product is excluded by the return policy" if item.variant_id in config["excluded"] else
                                "All purchased quantities are already requested or returned" if qty == 0 else None)
        remaining_value = max(Decimal(pools[item.id]) / 100 - value, Decimal(0))
        if item_reason is None and remaining_value <= 0:
            item_reason = "No refundable merchandise value remains for this item"
        result.append({"order_item_id": str(item.id), "product_name": item.product_name, "variant_sku": item.variant_sku,
                       "variant_attributes": item.variant_attributes, "purchased_quantity": item.quantity,
                       "available_quantity": qty, "eligible": item_reason is None, "ineligible_reason": item_reason,
                       "remaining_merchandise_amount": str(remaining_value)})
    return {"order_id": str(order.id), "eligible": any(item["eligible"] for item in result), "ineligible_reason": reason,
            "items": result, "available_refund_balance": str(funds),
            "policy": {key: value for key, value in config.items() if key != "excluded"},
            "reasons": [{"value": key, "label": value} for key, value in REASON_LABELS.items()],
            "refund_method": "manual_cod" if order.payment_method == "cod" else "original_payment"}


def record(session, row, action, actor=None, *, before=None, note=None, details=None, event_key=None):
    note = note[:1000] if note else note
    row.updated_at = utcnow()
    session.add(row)
    event = ReturnEvent(return_id=row.id, actor_id=actor.id if actor else None, action=action,
                        from_status=before, to_status=row.status.value, note=note, details=details or {}, event_key=event_key)
    session.add(event)
    audit.log(session, action=f"return.{action}", entity="return", entity_id=row.id,
              actor_id=actor.id if actor else None, before={"status": before},
              after={"status": row.status.value, "note": note, **(details or {})})


def attach_evidence(session, row, actor, images, written):
    existing = session.execute(select(func.count()).select_from(ReturnEvidence).where(ReturnEvidence.return_id == row.id)).scalar_one()
    if existing + len(images) > settings.RETURN_MAX_IMAGES:
        raise HTTPException(422, f"At most {settings.RETURN_MAX_IMAGES} images are allowed")
    for image in images:
        uploaded = upload_image(image["blob"], folder=f"com/returns/{row.id}", private=True, filename=image["filename"])
        written.append({"public_id": uploaded["public_id"], "private": True})
        evidence = ReturnEvidence(return_id=row.id, uploaded_by=actor.id, storage_key=uuid4().hex,
                                   filename=image["filename"], size_bytes=len(image["blob"]), sha256=image["hash"])
        evidence.secure_url = uploaded["secure_url"]
        evidence.cloudinary_public_id = uploaded["public_id"]
        evidence.cloudinary_type = uploaded.get("type")
        session.add(evidence)


def create_request(session, order_id, actor, data, images, written):
    order = owned_order(session, order_id, actor, lock=True)
    payload = data.model_dump(mode="json")
    payload["items"] = sorted(payload["items"], key=lambda item: item["order_item_id"])
    digest = hashlib.sha256(json.dumps({"order": str(order_id), "data": payload,
        "images": sorted(image["hash"] for image in images)}, sort_keys=True).encode()).hexdigest()
    existing = session.execute(select(ReturnRequest).where(ReturnRequest.user_id == actor.id,
        ReturnRequest.idempotency_key == str(data.idempotency_key))).scalars().first()
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, "This return submission key was used for different details")
        return existing
    check = eligibility(session, order, actor)
    choices = {UUID(item["order_item_id"]): item for item in check["items"]}
    if not check["eligible"]:
        raise HTTPException(409, check["ineligible_reason"] or "No eligible purchased quantities remain")
    if data.reason.value in check["policy"]["required_photo_reasons"] and not images:
        raise HTTPException(422, "The configured policy requires a photo for this reason")
    amounts = []
    for chosen in data.items:
        item = choices.get(chosen.order_item_id)
        if item is None:
            raise HTTPException(422, "A selected item does not belong to this order")
        if not item["eligible"]:
            raise HTTPException(409, item["ineligible_reason"])
        if chosen.quantity > item["available_quantity"]:
            raise HTTPException(409, "Requested quantity exceeds the remaining purchased quantity")
        # Allocate only from the remaining per-item cents; last quantity gets the residual.
        cents = int(Decimal(item["remaining_merchandise_amount"]) * 100)
        amount = Decimal(cents * chosen.quantity // item["available_quantity"]) / 100
        amounts.append((chosen, amount))
    gross = sum((amount for _, amount in amounts), Decimal(0))
    fee = money(gross * Decimal(str(check["policy"]["fee_percent"])) / 100)
    net = gross - fee
    if net <= 0 or net > Decimal(check["available_refund_balance"]):
        raise HTTPException(409, "Selected items exceed the unreserved refundable balance")
    row = ReturnRequest(order_id=order.id, user_id=actor.id, idempotency_key=str(data.idempotency_key),
                        payload_hash=digest, reason=data.reason, description=data.description,
                        refund_amount=net, return_fee=fee)
    session.add(row)
    session.flush()
    for chosen, amount in amounts:
        session.add(ReturnItem(return_id=row.id, order_item_id=chosen.order_item_id, quantity=chosen.quantity, amount=amount))
    attach_evidence(session, row, actor, images, written)
    record(session, row, "requested", actor, note=data.description,
           details={"reason": data.reason.value, "refund_amount": str(net), "return_fee": str(fee)})
    return row


def add_evidence(session, return_id, actor, images, written):
    row = get_request(session, return_id, owner=actor, lock=True)
    if row.status != ReturnStatus.REQUESTED:
        raise HTTPException(409, "Evidence can be added only before the return decision")
    if not images:
        raise HTTPException(422, "Select at least one image")
    attach_evidence(session, row, actor, images, written)
    record(session, row, "evidence_added", actor, before=row.status.value, details={"count": len(images)})
    return row


def decide(session, return_id, actor, data):
    require_permission(session, actor, "orders.update")
    row = get_request(session, return_id, lock=True)
    if row.status != ReturnStatus.REQUESTED:
        raise HTTPException(409, "Only requested returns can be approved or rejected")
    before = row.status.value
    row.decision_note = data.note
    if data.decision == "approve":
        row.status, row.approved_at = ReturnStatus.APPROVED, utcnow()
    else:
        row.status, row.rejected_at = ReturnStatus.REJECTED, utcnow()
    record(session, row, row.status.value, actor, before=before, note=data.note)
    return row


def cancel(session, return_id, actor, note="", *, admin=False):
    if admin:
        require_permission(session, actor, "orders.update")
    row = get_request(session, return_id, owner=None if admin else actor, lock=True)
    if row.status not in {ReturnStatus.REQUESTED, ReturnStatus.APPROVED}:
        raise HTTPException(409, "A return cannot be cancelled after shipping or receipt")
    before = row.status.value
    row.status, row.cancelled_at = ReturnStatus.CANCELLED, utcnow()
    record(session, row, "cancelled", actor, before=before, note=note)
    return row


def attach_tracking(session, return_id, actor, data, *, admin=False, managed=False):
    if admin:
        require_permission(session, actor, "orders.update", "shipping.manage")
    elif data.provider != "manual":
        raise HTTPException(403, "Only shipping admins may attach provider-managed return tracking")
    row = get_request(session, return_id, owner=None if admin else actor, lock=True)
    if row.shipping_requested_at and not managed:
        raise HTTPException(409, "Reconcile the existing Shiprocket reverse shipment before attaching other tracking")
    if row.status not in {ReturnStatus.APPROVED, ReturnStatus.RETURN_SHIPPED}:
        raise HTTPException(409, "Tracking can be attached only to an approved return")
    if row.tracking_number:
        if (row.tracking_number, row.courier_name, row.tracking_provider) == (data.tracking_number, data.courier_name, data.provider):
            return row
        raise HTTPException(409, "Tracking is already attached to this return")
    if session.execute(select(Order.id).where(Order.awb_code == data.tracking_number)).first() or session.execute(
            select(ReturnRequest.id).where(ReturnRequest.tracking_number == data.tracking_number)).first():
        raise HTTPException(409, "This tracking number is already associated with a shipment")
    before = row.status.value
    row.tracking_number, row.courier_name, row.tracking_provider = data.tracking_number, data.courier_name, data.provider
    # Creating a managed Shiprocket reverse shipment only books the pickup
    # and assigns an AWB. It does not prove the customer has handed the parcel
    # to the courier yet. The pickup webhook is the transition to
    # RETURN_SHIPPED. Manual tracking remains an explicit admin assertion that
    # an already-moving return was attached after the fact.
    action = "tracking_attached"
    if not managed:
        row.status, row.shipped_at = ReturnStatus.RETURN_SHIPPED, utcnow()
        action = "return_shipped"
    record(session, row, action, actor, before=before,
           details={"tracking_number": data.tracking_number, "courier_name": data.courier_name})
    return row


def receive(session, return_id, actor, note=""):
    require_permission(session, actor, "orders.update")
    row = get_request(session, return_id, lock=True)
    if row.status not in {ReturnStatus.APPROVED, ReturnStatus.RETURN_SHIPPED}:
        raise HTTPException(409, "Only an approved or shipped return can be received")
    before = row.status.value
    row.status, row.received_at = ReturnStatus.RECEIVED, utcnow()
    record(session, row, "received", actor, before=before, note=note)
    return row


def inspect(session, return_id, actor, data):
    require_permission(session, actor, "orders.update")
    row = get_request(session, return_id, lock=True)
    if row.status not in {ReturnStatus.RECEIVED, ReturnStatus.INSPECTION}:
        raise HTTPException(409, "Inspection requires physical receipt of the returned items")
    before = row.status.value
    row.status, row.inspection_passed = ReturnStatus.INSPECTION, data.passed
    row.inspected_at, row.inspection_note = utcnow(), data.note
    record(session, row, "inspection_passed" if data.passed else "inspection_failed", actor, before=before, note=data.note)
    return row


def validate_refund(session, order, return_id, amount, *, key, manual_reference=None, require_requested=False):
    """Also called by the existing pipeline at execution/approval boundaries."""
    row = get_request(session, return_id, lock=True)
    if order.cancelled_at or order.status not in {OrderStatus.DELIVERED, OrderStatus.REFUNDED}:
        raise HTTPException(409, "Product-return refunds require a delivered, uncancelled purchase")
    if row.order_id != order.id or row.inspection_passed is not True or row.received_at is None or row.status not in {
            ReturnStatus.INSPECTION, ReturnStatus.REFUND_PENDING, ReturnStatus.REFUNDED}:
        raise HTTPException(409, "A received return with passed inspection is required before refunding")
    if require_requested and row.status not in {ReturnStatus.REFUND_PENDING, ReturnStatus.REFUNDED}:
        raise HTTPException(409, "Start the item-level refund through the return workflow")
    if amount is None or money(amount) != row.refund_amount:
        raise HTTPException(409, "Return refund must match its captured item-level amount")
    existing = latest_refund(session, row)
    if existing and existing.status in {RefundStatus.EXECUTED, RefundStatus.PENDING_APPROVAL} and existing.idempotency_key != key:
        raise HTTPException(409, "A refund is already recorded or awaiting approval for this return")
    if order.payment_method == "cod" and not manual_reference:
        raise HTTPException(422, "Record the actual manual COD repayment reference")
    if order.payment_method != "cod" and manual_reference:
        raise HTTPException(422, "Online returns refund the original payment, not a manual transfer")
    payment = refund_service._get_refundable_payment(session, order)
    if payment is None or (order.payment_method == "cod") != (payment.provider == PaymentProvider.COD):
        raise HTTPException(409, "No matching collected payment is available for this return")
    if manual_reference and session.execute(select(Refund.id).where(
            Refund.order_id == order.id, Refund.manual_transfer_reference == manual_reference,
            Refund.idempotency_key != key, Refund.status.in_([RefundStatus.EXECUTED, RefundStatus.PENDING_APPROVAL]))).first():
        raise HTTPException(409, "This COD repayment reference is already recorded")
    if not existing or existing.status != RefundStatus.EXECUTED:
        pending = session.execute(select(func.coalesce(func.sum(Refund.amount), 0)).where(
            Refund.order_id == order.id, Refund.status == RefundStatus.PENDING_APPROVAL,
            Refund.idempotency_key != key)).scalar_one()
        balance = min(order.grand_total - order.restocking_fee, payment.amount) - order.refund_amount - pending
        if row.refund_amount > balance:
            raise HTTPException(409, "The captured payment no longer has this return's refundable balance")
    return row


def request_refund(session, return_id, actor, data):
    require_permission(session, actor, "orders.refund")
    row = get_request(session, return_id, lock=True)
    ledger = latest_refund(session, row)
    if row.status in {ReturnStatus.REFUND_PENDING, ReturnStatus.REFUNDED} and ledger and ledger.status in {
            RefundStatus.PENDING_APPROVAL, RefundStatus.EXECUTED}:
        return row
    if row.status != ReturnStatus.INSPECTION or row.inspection_passed is not True:
        raise HTTPException(409, "Refund requires receipt and an explicitly passed inspection")
    order = order_repo.get_order_by_id(session, row.order_id, for_update=True)
    row.refund_attempts += 1
    key = f"return-{row.id}-{row.refund_attempts}"
    validate_refund(session, order, row.id, row.refund_amount, key=key, manual_reference=data.manual_transfer_reference)
    before = row.status.value
    row.status, row.refund_requested_at = ReturnStatus.REFUND_PENDING, utcnow()
    record(session, row, "refund_requested", actor, before=before, details={"amount": str(row.refund_amount)})
    refund_service.request_admin_refund(session, order, actor, reason=f"Product return {row.id}: {REASON_LABELS[row.reason.value]}",
        amount=row.refund_amount, idempotency_key=key, status_at=OrderStatus.DELIVERED,
        commit=False, return_request_id=row.id, manual_transfer_reference=data.manual_transfer_reference)
    sync_order_returns(session, order)
    return row


def sync_order_returns(session, order):
    """Stage return completion/failure in the same transaction as ledger changes."""
    session.flush()
    for row in session.execute(select(ReturnRequest).where(ReturnRequest.order_id == order.id,
            ReturnRequest.status == ReturnStatus.REFUND_PENDING)).scalars():
        ledger = latest_refund(session, row)
        if not ledger:
            continue
        before = row.status.value
        if ledger.status == RefundStatus.EXECUTED and ledger.provider_status in refund_service.REFUND_COMPLETED_STATUSES:
            row.status, row.refunded_at = ReturnStatus.REFUNDED, utcnow()
            record(session, row, "refunded", before=before, details={"amount": str(ledger.amount), "refund_id": str(ledger.id)})
        elif ledger.status in {RefundStatus.FAILED, RefundStatus.REJECTED}:
            row.status = ReturnStatus.INSPECTION
            record(session, row, "refund_failed" if ledger.status == RefundStatus.FAILED else "refund_approval_rejected",
                   before=before, note="Refund attempt failed; awaiting an authorized retry" if ledger.status == RefundStatus.FAILED
                   else "Refund approval was rejected; awaiting review", details={"refund_id": str(ledger.id)})


def tracking_event(session, awb, data):
    row = session.execute(select(ReturnRequest).where(ReturnRequest.tracking_number == awb,
        ReturnRequest.tracking_provider == "shiprocket")).scalars().first()
    if row is None:
        return None
    row = get_request(session, row.id, lock=True)
    label = normalize_status(data.get("current_status") or data.get("shipment_status"))[:100]
    location = normalize_location(data.get("location"))[:200]
    date = str(data.get("date") or "")[:100]
    key = "return:" + str(row.id) + ":scan:" + hashlib.sha256(json.dumps([label, location, date]).encode()).hexdigest()
    if not session.execute(select(ReturnEvent.id).where(ReturnEvent.event_key == key)).first():
        before = row.status.value
        target, _ = map_shiprocket_status(label)
        # AWB assignment/label generation is still pre-pickup. A pickup scan,
        # or a later transit scan when the courier omits the pickup scan, is
        # the first provider evidence that the parcel actually left the
        # customer's possession.
        pickup_labels = {
            "PICKED UP", "ORDER PICKED", "RETURN PICKED UP", "RETURN_PICKED_UP",
            "IN TRANSIT", "RETURN IN TRANSIT", "SHIPPED", "DISPATCHED",
        }
        if row.status == ReturnStatus.APPROVED and label in pickup_labels:
            row.status, row.shipped_at = ReturnStatus.RETURN_SHIPPED, utcnow()
            record(session, row, "return_shipped", before=before,
                   details={"status": label, "location": location, "date": date})
            before = row.status.value
        if row.status in {ReturnStatus.APPROVED, ReturnStatus.RETURN_SHIPPED} and target == OrderStatus.DELIVERED and label in {
                "DELIVERED", "RETURN DELIVERED", "RETURN_DELIVERED"}:
            row.status, row.received_at = ReturnStatus.RECEIVED, utcnow()
        if row.status not in TERMINAL:
            row.tracking_status = label or "UNKNOWN"
        record(session, row, "tracking_scan", before=before, event_key=key,
               details={"status": label, "location": location, "date": date})
    return {"status": "success", "return_id": str(row.id), "return_status": row.status.value}


def read_request(session, row, *, admin=False):
    order = order_repo.get_order_by_id(session, row.order_id)
    items = session.execute(select(ReturnItem, OrderItem).join(OrderItem, ReturnItem.order_item_id == OrderItem.id)
                            .where(ReturnItem.return_id == row.id).order_by(ReturnItem.id)).all()
    images = session.execute(select(ReturnEvidence).where(ReturnEvidence.return_id == row.id)
                             .order_by(ReturnEvidence.created_at, ReturnEvidence.id)).scalars().all()
    events = session.execute(select(ReturnEvent).where(ReturnEvent.return_id == row.id)
                             .order_by(ReturnEvent.created_at, ReturnEvent.id)).scalars().all()
    ledger = latest_refund(session, row)
    result = row.model_dump(mode="json", exclude={"payload_hash", "idempotency_key", "refund_attempts"})
    result.update({"return_number": "RET-" + row.id.hex[:12].upper(), "order_number": order.order_number,
        "reason_label": REASON_LABELS[row.reason.value], "payment_method": order.payment_method,
        "items": [{"order_item_id": str(item.id), "product_name": item.product_name, "variant_sku": item.variant_sku,
                   "variant_attributes": item.variant_attributes, "quantity": returned.quantity, "amount": str(returned.amount)}
                  for returned, item in items],
        "evidence": [{"id": str(image.id), "filename": image.filename, "size_bytes": image.size_bytes} for image in images],
        "history": [{"action": event.action, "from_status": event.from_status, "to_status": event.to_status,
                     "note": event.note, "details": event.details, "created_at": event.created_at.isoformat()} for event in events],
        "refund": {"id": str(ledger.id), "status": ledger.status.value, "amount": str(ledger.amount),
                   "provider_status": ledger.provider_status, "provider_refund_id": ledger.provider_refund_id,
                   "requires_approval": ledger.status == RefundStatus.PENDING_APPROVAL} if ledger else None})
    if admin:
        customer = order.customer_details
        if result["refund"]:
            result["refund"]["manual_transfer_reference"] = ledger.manual_transfer_reference
        result["customer"] = {"id": str(order.user_id), "name": getattr(customer, "full_name", None) or getattr(customer, "username", None),
                              "email": getattr(customer, "email", None)}
    return result


def list_requests(session, *, owner=None, page=1, limit=20, status=None, reason=None, search=None, order_id=None):
    query = select(ReturnRequest).join(Order, ReturnRequest.order_id == Order.id).join(User, ReturnRequest.user_id == User.id)
    if owner is not None:
        query = query.where(ReturnRequest.user_id == owner.id)
    if status:
        query = query.where(ReturnRequest.status == status)
    if reason:
        query = query.where(ReturnRequest.reason == reason)
    if order_id:
        query = query.where(ReturnRequest.order_id == order_id)
    if search:
        term = "%" + search.replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(Order.order_number.ilike(term, escape="\\"), User.email.ilike(term, escape="\\"),
                                User.full_name.ilike(term, escape="\\"), User.username.ilike(term, escape="\\")))
    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = session.execute(query.order_by(ReturnRequest.created_at.desc(), ReturnRequest.id).offset((page - 1) * limit).limit(limit)).scalars().all()
    return {"returns": [read_request(session, row, admin=owner is None) for row in rows], "total": total,
            "page": page, "limit": limit, "total_pages": max((total + limit - 1) // limit, 1)}
