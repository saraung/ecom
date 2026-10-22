"""Reverse booking with durable checkpoints, separate from financial state."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models.order import Order, OrderItem
from app.models.product_return import ReturnItem, ReturnStatus, utcnow
from app.schemas.product_return import ReturnTracking
from app.services import product_return as returns
from app.services.shiprocket_service import PickupRequestRejected, ReturnCreationRejected, get_shipping_service


def _request_pickup(session, row, actor, provider):
    """Request reverse pickup once, with a durable pre-call checkpoint.

    The provider call is an external side effect. Persisting the checkpoint
    before calling Shiprocket prevents a lost response from causing a second
    pickup request on the next admin click. A definite provider rejection
    clears the checkpoint so the same shipment can be retried safely; an
    unknown outcome remains checkpointed for reconciliation instead.
    """
    if row.pickup_requested_at:
        return row
    if not row.shiprocket_shipment_id or not row.tracking_number:
        raise HTTPException(409, "Assign a reverse AWB before requesting pickup")

    row.pickup_requested_at = utcnow()
    returns.record(session, row, "pickup_request_started", actor,
                   details={"shipment_id": row.shiprocket_shipment_id})
    session.commit()
    row = returns.get_request(session, row.id, lock=True)
    returns.require_permission(session, actor, "orders.update", "shipping.manage")

    try:
        result = provider.request_pickup(row.shiprocket_shipment_id)
    except PickupRequestRejected as exc:
        row.pickup_requested_at = None
        returns.record(session, row, "pickup_request_rejected", actor, note=str(exc),
                       details={"shipment_id": row.shiprocket_shipment_id})
        session.commit()
        raise HTTPException(502, str(exc))
    except Exception:
        raise HTTPException(502, "Reverse AWB is saved, but pickup scheduling outcome is unknown; verify Shiprocket before retrying")

    row = returns.get_request(session, row.id, lock=True)
    returns.require_permission(session, actor, "orders.update", "shipping.manage")
    returns.record(session, row, "pickup_requested", actor,
                   details={"shipment_id": row.shiprocket_shipment_id,
                            "provider_status": result.get("pickup_status") if isinstance(result, dict) else None,
                            "pickup_scheduled_date": result.get("pickup_scheduled_date") if isinstance(result, dict) else None})
    session.commit()
    return returns.get_request(session, row.id, lock=True)


def create_shipment(session, return_id, actor):
    returns.require_permission(session, actor, "orders.update", "shipping.manage")
    row = returns.get_request(session, return_id, lock=True)
    if row.shiprocket_order_id and row.tracking_number:
        # A repeated booking never regresses received/inspected returns. If a
        # prior attempt attached the AWB before pickup scheduling, resume that
        # missing provider step instead of assigning another AWB.
        if row.status == ReturnStatus.APPROVED and not row.pickup_requested_at:
            return _request_pickup(session, row, actor, get_shipping_service())
        return row
    if row.status != ReturnStatus.APPROVED or row.tracking_number:
        raise HTTPException(409, "Create a reverse shipment only for an approved return without tracking")
    provider = get_shipping_service()
    reference = row.shipping_reference or ("9" + str(row.id.int % (10 ** 19)).zfill(19))
    try:
        found = provider.get_return_order(row.shiprocket_order_id, reference) if row.shiprocket_order_id else provider.find_return_order(reference)
    except Exception:
        raise HTTPException(502, "Shiprocket return lookup is unavailable; no new shipment was created")
    if not found:
        if row.shipping_requested_at:
            raise HTTPException(409, "Return creation is awaiting provider reconciliation. Retry lookup or confirm the reference in Shiprocket; a second shipment will not be created")
        row.shipping_reference, row.shipping_requested_at = reference, utcnow()
        returns.record(session, row, "shipping_creation_requested", actor, details={"reference": reference})
        # Persist BEFORE the external side effect. An interrupted/lost response
        # can only reconcile this reference, never automatically POST it again.
        session.commit()
        row = returns.get_request(session, return_id, lock=True)
        returns.require_permission(session, actor, "orders.update", "shipping.manage")
        if row.status != ReturnStatus.APPROVED:
            raise HTTPException(409, "Return is no longer approved for shipping")
        order = session.get(Order, row.order_id)
        items = session.execute(select(ReturnItem, OrderItem).join(OrderItem, ReturnItem.order_item_id == OrderItem.id)
                                .where(ReturnItem.return_id == row.id)).all()
        payload = [{"name": item.product_name, "sku": item.variant_sku or "SKU-DEFAULT", "units": returned.quantity,
                    "selling_price": str(item.unit_price), "discount": "0", "hsn": ""} for returned, item in items]
        try:
            found = provider.create_return_order(order, reference, payload)
        except ReturnCreationRejected as exc:
            row.shipping_requested_at = None
            returns.record(session, row, "shipping_creation_rejected", actor, note=str(exc))
            session.commit()
            raise HTTPException(502, str(exc))
        except Exception:
            raise HTTPException(502, "Return creation outcome is unknown; retry to reconcile the saved reference without creating another shipment")
    order = session.get(Order, row.order_id)
    order_id, shipment_id = str(found.get("order_id") or ""), str(found.get("shipment_id") or "")
    if not order_id or not shipment_id or order_id == order.shiprocket_order_id or shipment_id == order.shiprocket_shipment_id:
        raise HTTPException(502, "Provider returned invalid or forward-shipment identifiers for this return")
    if row.shiprocket_shipment_id and shipment_id != row.shiprocket_shipment_id:
        raise HTTPException(502, "Provider return shipment does not match the saved reverse shipment")
    if not row.shiprocket_order_id:
        row.shipping_reference, row.shipping_requested_at = reference, row.shipping_requested_at or utcnow()
        row.shiprocket_order_id, row.shiprocket_shipment_id = order_id, shipment_id
        returns.record(session, row, "shipping_created", actor, details={"order_id": order_id, "shipment_id": shipment_id})
        # AWB assignment can fail independently (balance/serviceability). Retain
        # the accepted identifiers so the next action resumes this shipment.
        session.commit()
        row = returns.get_request(session, return_id, lock=True)
        returns.require_permission(session, actor, "orders.update", "shipping.manage")
    if row.tracking_number:
        return row
    if row.status != ReturnStatus.APPROVED:
        raise HTTPException(409, "Return is no longer approved for AWB assignment")
    try:
        # Re-query after the checkpoint: recover an AWB accepted before a lost
        # response/failed commit, and serialize assignment under the parent lock.
        live = provider.get_return_order(order_id, reference)
        if str(live.get("shipment_id")) != shipment_id:
            raise ValueError("Return shipment mismatch")
        assigned = live if live.get("awb_code") else provider.assign_awb(shipment_id, is_return=True)
        tracking = ReturnTracking(tracking_number=assigned.get("awb_code"), courier_name=assigned.get("courier_name") or "Shiprocket", provider="shiprocket")
    except Exception:
        raise HTTPException(502, "Reverse shipment is saved; retry this action to reconcile or assign its return AWB")
    row = returns.attach_tracking(session, return_id, actor, tracking, admin=True, managed=True)
    return _request_pickup(session, row, actor, provider)
