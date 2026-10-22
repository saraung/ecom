from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select

from app.core.config import settings
from app.api.deps import SessionDep, require_perm
from app.api.v1.returns import evidence_response, mutation
from app.api.v1.webhooks import process_tracking_event
from app.models.product_return import ReturnReason, ReturnRequest, ReturnStatus
from app.models.user import User
from app.repositories import order as order_repo
from app.schemas.order import SimulatorTriggerWebhookRequest
from app.schemas.product_return import ReturnDecision, ReturnInspection, ReturnNote, ReturnRefundInput, ReturnTracking
from app.services import product_return as service
from app.services.shiprocket_service import get_shipping_service
from app.services import return_shipping
from app.services.shipping_status import build_tracking_webhook_payload

router = APIRouter(prefix="/admin/returns", tags=["Admin Product Returns"])

RETURN_SIMULATOR_EVENTS = {"picked_up": "RETURN PICKED UP", "in_transit": "RETURN IN TRANSIT",
                           "out_for_delivery": "RETURN OUT FOR DELIVERY", "delivered": "RETURN DELIVERED"}


@router.get("/shipping/simulator/shipments")
def simulator_returns(session: SessionDep, current_user: User = Depends(require_perm("orders.view", "shipping.manage"))):
    rows = session.execute(select(ReturnRequest).where(or_(ReturnRequest.shiprocket_order_id.is_not(None),
                           (ReturnRequest.tracking_provider == "shiprocket") & ReturnRequest.tracking_number.is_not(None)))
                           .order_by(ReturnRequest.updated_at.desc())).scalars().all()
    result = []
    for row in rows:
        detail = service.read_request(session, row, admin=True)
        result.append({"shipment_type": "return", "return_id": str(row.id), "return_number": detail["return_number"],
                       "order_id": str(row.order_id), "order_number": detail["order_number"],
                       "user_name": detail["customer"]["name"], "shiprocket_order_id": row.shiprocket_order_id,
                       "shiprocket_shipment_id": row.shiprocket_shipment_id, "awb_code": row.tracking_number,
                       "courier_name": row.courier_name, "return_status": row.status.value,
                       "reason_label": detail["reason_label"],
                       "items": [{"product_name": item["product_name"], "quantity": item["quantity"]} for item in detail["items"]],
                       "tracking_status": row.tracking_status,
                       "tracking_scans_count": sum(entry["action"] == "tracking_scan" for entry in detail["history"])})
    return {"shipments": result, "provider": settings.SHIPPING_PROVIDER}


@router.post("/{return_id}/shipping/simulator/trigger-event")
def simulate_return(return_id: UUID, data: SimulatorTriggerWebhookRequest, session: SessionDep,
                    current_user: User = Depends(require_perm("orders.update", "shipping.manage"))):
    if settings.SHIPPING_PROVIDER.lower() != "simulator":
        raise HTTPException(409, "Return event simulation is available only with the simulator shipping provider")
    row = service.get_request(session, return_id, lock=True)
    if not row.tracking_number or row.tracking_provider != "shiprocket":
        raise HTTPException(409, "Create a Shiprocket return or attach its own Shiprocket AWB before simulating events")
    label = RETURN_SIMULATOR_EVENTS.get(data.event.strip().lower())
    if label is None:
        raise HTTPException(422, "Choose a return pickup, transit, out-for-delivery or delivered event; outbound RTO is separate")
    order = order_repo.get_order_by_id(session, row.order_id)
    before = {"return_status": row.status.value, "tracking_status": row.tracking_status,
              "received_at": row.received_at.isoformat() if row.received_at else None,
              "inspection_passed": row.inspection_passed, "refund": service.latest_refund(session, row) is not None,
              "forward_awb": order.awb_code if order else None}
    payload = build_tracking_webhook_payload(awb=row.tracking_number, current_status=label, is_return=1,
        location=data.location or "Return Delivery Hub", activity=data.activity or f"Return shipment: {label}")
    result = process_tracking_event(session, payload)
    session.refresh(row)
    if order:
        session.refresh(order)
    after = {"return_status": row.status.value, "tracking_status": row.tracking_status,
             "received_at": row.received_at.isoformat() if row.received_at else None,
             "inspection_passed": row.inspection_passed, "refund": service.latest_refund(session, row) is not None,
             "forward_awb": order.awb_code if order else None}
    return {**result, "simulated_payload": payload, "status_changed": before["return_status"] != after["return_status"],
            "before": before, "after": after,
            "effects": {"return_received_now": before["return_status"] != "received" and after["return_status"] == "received",
                        "inspection_unchanged": before["inspection_passed"] == after["inspection_passed"],
                        "refund_unchanged": before["refund"] == after["refund"],
                        "forward_awb_preserved": before["forward_awb"] == after["forward_awb"]}}


@router.get("")
def list_returns(session: SessionDep, current_user: User = Depends(require_perm("orders.view")),
                 page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1, le=100),
                 status_filter: ReturnStatus | None = None, reason: ReturnReason | None = None,
                 search: str | None = Query(default=None, max_length=200), order_id: UUID | None = None):
    return service.list_requests(session, page=page, limit=limit, status=status_filter, reason=reason, search=search, order_id=order_id)


@router.get("/{return_id}")
def return_detail(return_id: UUID, session: SessionDep, current_user: User = Depends(require_perm("orders.view"))):
    return service.read_request(session, service.get_request(session, return_id), admin=True)


@router.get("/{return_id}/evidence/{evidence_id}")
def download_evidence(return_id: UUID, evidence_id: UUID, session: SessionDep,
                      current_user: User = Depends(require_perm("orders.view"))):
    service.get_request(session, return_id)
    return evidence_response(session, return_id, evidence_id)


@router.post("/{return_id}/decision")
def decide_return(return_id: UUID, data: ReturnDecision, session: SessionDep,
                  current_user: User = Depends(require_perm("orders.update"))):
    return mutation(session, lambda: service.decide(session, return_id, current_user, data), admin=True)


@router.post("/{return_id}/cancel")
def cancel_return(return_id: UUID, data: ReturnNote, session: SessionDep,
                  current_user: User = Depends(require_perm("orders.update"))):
    return mutation(session, lambda: service.cancel(session, return_id, current_user, data.note, admin=True), admin=True)


@router.post("/{return_id}/tracking")
def attach_tracking(return_id: UUID, data: ReturnTracking, session: SessionDep,
                    current_user: User = Depends(require_perm("orders.update", "shipping.manage"))):
    return mutation(session, lambda: service.attach_tracking(session, return_id, current_user, data, admin=True), admin=True)


@router.post("/{return_id}/shipping/shiprocket")
def create_return_shipment(return_id: UUID, session: SessionDep,
                           current_user: User = Depends(require_perm("orders.update", "shipping.manage"))):
    return mutation(session, lambda: return_shipping.create_shipment(session, return_id, current_user), admin=True)


@router.post("/{return_id}/tracking/sync")
def sync_tracking(return_id: UUID, session: SessionDep,
                  current_user: User = Depends(require_perm("orders.update", "shipping.manage"))):
    row = service.get_request(session, return_id)
    if not row.tracking_number or row.tracking_provider != "shiprocket":
        raise HTTPException(409, "Attach a Shiprocket return AWB before syncing provider tracking")
    try:
        live = get_shipping_service().get_tracking(row.tracking_number)
    except Exception:
        raise HTTPException(502, "Return tracking provider is temporarily unavailable")
    if not isinstance(live, dict) or not isinstance(live.get("tracking_data"), dict):
        raise HTTPException(502, "Return tracking provider returned an invalid response")
    tracking = live["tracking_data"]
    scans = tracking.get("shipment_track_activities") or tracking.get("shipment_track") or []
    if not isinstance(scans, list) or any(not isinstance(scan, dict) for scan in scans):
        raise HTTPException(502, "Return tracking provider returned invalid scans")
    def apply():
        for scan in scans:
            service.tracking_event(session, row.tracking_number, {
                "current_status": scan.get("sr-status-label") or scan.get("current_status") or scan.get("status"),
                "date": scan.get("date"), "location": scan.get("location")})
        return service.get_request(session, return_id)
    return mutation(session, apply, admin=True)


@router.post("/{return_id}/receive")
def receive_return(return_id: UUID, data: ReturnNote, session: SessionDep,
                   current_user: User = Depends(require_perm("orders.update"))):
    return mutation(session, lambda: service.receive(session, return_id, current_user, data.note), admin=True)


@router.post("/{return_id}/inspection")
def inspect_return(return_id: UUID, data: ReturnInspection, session: SessionDep,
                   current_user: User = Depends(require_perm("orders.update"))):
    return mutation(session, lambda: service.inspect(session, return_id, current_user, data), admin=True)


@router.post("/{return_id}/refund")
def refund_return(return_id: UUID, data: ReturnRefundInput, session: SessionDep,
                  current_user: User = Depends(require_perm("orders.refund"))):
    return mutation(session, lambda: service.request_refund(session, return_id, current_user, data), admin=True)
