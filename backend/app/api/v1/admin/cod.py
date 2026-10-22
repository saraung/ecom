# app/api/v1/admin/cod.py
"""
Admin endpoints for Cash on Delivery (COD) orders.

COD lifecycle:
  checkout (payment_method=cod) -> order.status=confirmed, payment_status="cod_pending"
  cash collected on delivery    -> POST /admin/cod/orders/{id}/collect
                                -> payment_status="paid" + COD payment record created
"""
from datetime import datetime, timezone
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlmodel import Session

from app.api.deps import SessionDep, require_perm
from app.core.region import currency_code
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.repositories import order as order_repo
from app.repositories import audit as audit_repo
from app.schemas.cod_remittance import (
    BulkCollectRequest,
    ConfirmReceiptRequest,
    ManualBatchCreate,
    ResolveItemRequest,
)
from app.services import cod_remittance as remittance_service

router = APIRouter(prefix="/admin/cod", tags=["Admin COD"])


@router.get("/pending")
def get_pending_cod_orders(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.update")),
):
    """
    List all COD orders waiting for cash collection.
    """
    statement = (
        select(Order)
        .where(Order.payment_method == "cod")
        .where(Order.payment_status == "cod_pending")
        .where(Order.status.notin_([OrderStatus.CANCELLED, OrderStatus.REFUNDED, OrderStatus.RTO]))
        .order_by(Order.placed_at.desc())
        .options(
            selectinload(Order.user),
            selectinload(Order.items),
        )
    )
    orders = session.execute(statement).scalars().all()

    return {
        "count": len(orders),
        "total_pending_amount": float(sum(o.grand_total for o in orders)),
        "orders": [
            {
                "id": str(o.id),
                "order_number": o.order_number,
                "customer": {
                    "id": str(o.customer_details.id),
                    "full_name": o.customer_details.full_name,
                    "email": o.customer_details.email,
                    "phone": o.customer_details.phone,
                } if o.customer_details else None,
                "grand_total": float(o.grand_total),
                "cod_fee": float(o.cod_fee or 0),
                "status": o.status.value if hasattr(o.status, "value") else str(o.status),
                "payment_status": o.payment_status,
                "collectible": o.status == OrderStatus.DELIVERED,
                "placed_at": o.placed_at.isoformat() if o.placed_at else None,
            }
            for o in orders
        ],
    }


def record_cod_collection(
    session: Session,
    order: Order,
    *,
    actor_id: UUID | None = None,
    collected_by_email: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """
    Record COD cash collection as a real COD Payment, idempotently.

    Creates exactly one COD Payment (status=succeeded) and flips the order to
    payment_status="paid". Raises HTTPException when the order is ineligible or
    already collected — never creates a second Payment and never double-counts
    revenue.

    Stages the audit entry but does NOT commit: the caller owns the transaction
    so the payment, order mutation and audit row commit together atomically.
    """
    if order.payment_method != "cod":
        raise HTTPException(
            status_code=400,
            detail="Order was not placed with Cash on Delivery",
        )

    if order.payment_status == "paid":
        raise HTTPException(status_code=409, detail="COD payment already collected")

    if order.payment_status != "cod_pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot collect COD for order with payment_status '{order.payment_status}'",
        )

    if order.status != OrderStatus.DELIVERED:
        raise HTTPException(status_code=400, detail="COD can only be collected for a delivered order")

    existing = session.execute(select(Payment).where(
        Payment.order_id == order.id, Payment.provider == PaymentProvider.COD,
        Payment.status == PaymentStatus.SUCCEEDED,
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="COD payment already recorded; reconcile order state")

    now = datetime.now(timezone.utc)
    payment = Payment(
        order_id=order.id,
        provider=PaymentProvider.COD,
        provider_payment_id=f"cod_{order.order_number}",
        amount=order.grand_total,
        currency=currency_code(),
        status=PaymentStatus.SUCCEEDED,
        payment_method="cod",
        paid_at=now,
        payment_metadata={
            "collected_by": str(actor_id) if actor_id else "shiprocket-webhook",
            "collected_by_email": collected_by_email or ("shiprocket-webhook" if actor_id is None else ""),
            "collected_at": now.isoformat(),
            "source": "webhook" if actor_id is None else "admin",
        },
    )
    session.add(payment)

    order.payment_status = "paid"
    session.add(order)
    audit_repo.log(
        session,
        "cod.collected",
        "order",
        order.id,
        actor_id,
        before={"payment_status": "cod_pending"},
        after={
            "payment_status": "paid",
            "amount": str(order.grand_total),
            "payment_id": str(payment.id),
            "source": payment.payment_metadata["source"],
        },
        ip_address=ip_address,
    )
    session.flush()

    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "amount_collected": float(order.grand_total),
        "payment_status": order.payment_status,
        "collected_by": collected_by_email or ("shiprocket-webhook" if actor_id is None else str(actor_id)),
    }


@router.post("/orders/{order_id}/collect", status_code=status.HTTP_200_OK)
def collect_cod_payment(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.update")),
    request: Request = None,
):
    """
    Mark a COD order's cash as COLLECTED ON DELIVERY.

    - Creates a COD payment record (status=succeeded)
    - Flips the order to payment_status="paid"
    """
    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    result = record_cod_collection(
        session,
        order,
        actor_id=current_user.id,
        collected_by_email=current_user.email,
        ip_address=audit_repo.client_ip(request),
    )
    session.commit()
    session.refresh(order)

    print(f"✅ COD collected for order {order.order_number} by {current_user.email}")

    return {
        "message": "COD payment collected successfully",
        **result,
    }


# =========================================================
# COD REMITTANCE RECONCILIATION
# =========================================================
#
# Customer collection (above) and courier remittance (below) are deliberately
# separate events. Remittance endpoints NEVER create a Payment row: the cash
# Payment already exists from collection, and adding another would double-count
# revenue.


@router.get("/summary")
def cod_reconciliation_summary(
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.view")),
):
    return remittance_service.get_summary(session)


@router.get("/awaiting-remittance")
def cod_orders_awaiting_remittance(
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.view")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=15, ge=1, le=100),
):
    """List delivered COD orders whose customer cash is collected but payout is outstanding."""
    return remittance_service.list_awaiting_remittance(session, page=page, limit=limit)


@router.post("/collect-bulk")
def collect_cod_bulk(
    data: BulkCollectRequest,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("orders.update")),
):
    """Mark several delivered COD orders' cash as collected.

    Each order still goes through the single-order collection path, so the
    payment/audit rules (delivered-only, exactly once) are unchanged.
    """
    results = []
    for order_id in data.order_ids:
        try:
            outcome = collect_cod_payment(order_id, session, current_user, request)
            results.append({"order_id": str(order_id), "ok": True, "message": outcome["message"]})
        except HTTPException as exc:
            results.append({"order_id": str(order_id), "ok": False, "message": str(exc.detail)})
        except Exception as exc:  # keep the batch report useful
            results.append({"order_id": str(order_id), "ok": False, "message": str(exc)})
    return {
        "collected": sum(1 for row in results if row["ok"]),
        "failed": sum(1 for row in results if not row["ok"]),
        "results": results,
    }


@router.get("/remittances")
def list_cod_remittances(
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.view")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
):
    return remittance_service.list_batches(
        session, page=page, limit=limit, status=status_filter, search=search
    )


@router.get("/remittances/sample-template")
def cod_remittance_template(
    current_user: User = Depends(require_perm("cod.view")),
):
    return Response(
        content=remittance_service.template_csv(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cod-remittance-template.csv"'},
    )


@router.get("/remittances/sample-fixture")
def cod_remittance_fixture(
    current_user: User = Depends(require_perm("cod.view")),
):
    return Response(
        content=remittance_service.fixture_csv(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="SYNTHETIC_cod_remittance_fixture.csv"',
            "X-Data-Note": "SYNTHETIC - not real Shiprocket data",
        },
    )


def _parse_mapping(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Column mapping must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(400, "Column mapping must be an object")
    return {str(k): (str(v) if v else None) for k, v in parsed.items()}


@router.post("/remittances/import/preview")
async def preview_cod_remittance(
    session: SessionDep,
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    current_user: User = Depends(require_perm("cod.reconcile")),
):
    data = await file.read(remittance_service.MAX_CSV_BYTES + 1)
    return remittance_service.preview_csv(session, data, _parse_mapping(mapping))


@router.post("/remittances/import")
async def import_cod_remittance(
    request: Request,
    session: SessionDep,
    file: UploadFile = File(...),
    crf_id: str = Form(..., max_length=120),
    remittance_date: str = Form(...),
    mapping: str | None = Form(default=None),
    notes: str | None = Form(default=None, max_length=4000),
    current_user: User = Depends(require_perm("cod.reconcile")),
):
    parsed_date = remittance_service.parse_date(remittance_date)
    if parsed_date is None:
        raise HTTPException(400, "Remittance date must be YYYY-MM-DD (or DD-MM-YYYY)")
    data = await file.read(remittance_service.MAX_CSV_BYTES + 1)
    headers, rows = remittance_service.parse_csv_bytes(data)
    active_mapping = _parse_mapping(mapping) or remittance_service.suggest_mapping(headers)
    active_mapping = {k: v for k, v in active_mapping.items() if v}
    lines = remittance_service.normalize_rows(rows, active_mapping)
    if not lines:
        raise HTTPException(400, "No remittance lines with an AWB or order number were found")
    source_filename = (file.filename or "").strip()[:255] or None
    return remittance_service.create_batch(
        session,
        current_user,
        crf_id=crf_id,
        remittance_date=parsed_date,
        lines=lines,
        source="csv",
        source_filename=source_filename,
        notes=notes,
        mapping=active_mapping,
        ip_address=audit_repo.client_ip(request),
    )


@router.post("/remittances")
def create_manual_cod_remittance(
    data: ManualBatchCreate,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.reconcile")),
):
    lines = remittance_service.normalize_manual_items(data.items)
    return remittance_service.create_batch(
        session,
        current_user,
        crf_id=data.crf_id,
        remittance_date=data.remittance_date,
        lines=lines,
        source="manual",
        notes=data.notes,
        mapping={},
        ip_address=audit_repo.client_ip(request),
    )


@router.post("/remittances/simulate")
def simulate_cod_remittance(
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.reconcile")),
    max_orders: int = Query(default=5, ge=1, le=25),
):
    """Create a clearly-labelled synthetic batch for development/testing."""
    return remittance_service.simulate_batch(
        session,
        current_user,
        max_orders=max_orders,
        ip_address=audit_repo.client_ip(request),
    )


@router.get("/remittances/{remittance_id}")
def get_cod_remittance(
    remittance_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.view")),
):
    batch = remittance_service._get_batch(session, remittance_id)
    return remittance_service.batch_detail(session, batch)


@router.get("/remittances/{remittance_id}/export")
def export_cod_remittance(
    remittance_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.view")),
):
    batch = remittance_service._get_batch(session, remittance_id)
    safe_ref = re.sub(r"[^A-Za-z0-9._-]+", "_", batch.crf_id).strip("_") or "batch"
    return Response(
        content=remittance_service.batch_csv(session, batch),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="cod-remittance-{safe_ref}.csv"'
        },
    )


@router.post("/remittances/{remittance_id}/resolve")
def resolve_cod_remittance_item(
    remittance_id: UUID,
    data: ResolveItemRequest,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.reconcile")),
):
    return remittance_service.resolve_item(
        session,
        current_user,
        remittance_id,
        data.item_id,
        data.action,
        data.note,
        ip_address=audit_repo.client_ip(request),
    )


@router.post("/remittances/{remittance_id}/confirm")
def confirm_cod_remittance(
    remittance_id: UUID,
    data: ConfirmReceiptRequest,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.reconcile")),
):
    return remittance_service.confirm_bank_receipt(
        session,
        current_user,
        remittance_id,
        utr=data.utr,
        bank_credit_amount=data.bank_credit_amount,
        bank_credit_date=data.bank_credit_date,
        bank_account_ref=data.bank_account_ref,
        notes=data.notes,
        accept_difference=data.accept_difference,
        difference_reason=data.difference_reason,
        ip_address=audit_repo.client_ip(request),
    )


@router.post("/remittances/{remittance_id}/void")
def void_cod_remittance(
    remittance_id: UUID,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("cod.reconcile")),
    note: str | None = Query(default=None, max_length=1000),
):
    return remittance_service.void_batch(
        session,
        current_user,
        remittance_id,
        note,
        ip_address=audit_repo.client_ip(request),
    )
