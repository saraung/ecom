# app/api/v1/admin/orders.py
from uuid import UUID
from datetime import date, datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.api.deps import SessionDep, require_perm
from app.api.v1.webhooks import process_tracking_event
from app.models.user import User
from app.models.order import Order, OrderStatus
from app.models.product import ProductVariant
from app.repositories import order as order_repo
from app.repositories import notification as notification_repo
from app.repositories import product_image as product_image_repo
from app.schemas.order import OrderRead, OrderStatusUpdate, OrderListRead
from app.services.email_outbox import enqueue_order_email
from app.services.refund_service import restore_stock
from app.services.shipping_status import (
    build_tracking_webhook_payload,
    normalize_location,
    simulation_state,
    shipment_stage_payload,
)
from app.core.config import settings
from app.core.region import format_money
from app.services.order_snapshot import order_details

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


@router.get("", response_model=dict)
def get_all_orders_admin(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.view")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """
    Get all orders with filters and pagination.
    
    Allowed:
        manager
        admin
    """
    skip = (page - 1) * limit
    
    orders, total = order_repo.get_all_orders_with_filters(
        session=session,
        skip=skip,
        limit=limit,
        status=status,
        search=search,
        from_date=from_date,
        to_date=to_date,
    )
    
    # Manually convert orders to dict with user data
    orders_data = []
    for order in orders:
        details = order_details(order)
        user_data = details["user"]
        shipping_address_data = details["shipping_address"]
        billing_address_data = details["billing_address"]
        
        # Build order dictionary
        order_dict = {
            "id": str(order.id),
            "order_number": order.order_number,
            "user_id": str(order.user_id),
            
            # User data
            "user": user_data,
            
            # Address data
            "shipping_address": shipping_address_data,
            "billing_address": billing_address_data,
            "shipping_address_id": str(order.shipping_address_id),
            "billing_address_id": str(order.billing_address_id),
            
            # Financials
            "subtotal": float(order.subtotal) if order.subtotal else 0,
            "discount_total": float(order.discount_total) if order.discount_total else 0,
            "tax_total": float(order.tax_total) if order.tax_total else 0,
            "shipping_total": float(order.shipping_total) if order.shipping_total else 0,
            "grand_total": float(order.grand_total) if order.grand_total else 0,
            
            # Status
            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
            "payment_status": order.payment_status,
            "coupon_code": order.coupon_code,
            # Shipping / Shiprocket
            "awb_code": order.awb_code,
            "courier_name": order.courier_name,
            "shipment_status": order.shipment_status,
            "shiprocket_order_id": order.shiprocket_order_id,

            
            # Cancellation
            "cancellation_reason": order.cancellation_reason,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
            
            # Timestamps
            "placed_at": order.placed_at.isoformat() if order.placed_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            
            # Items
            "items": [
                {
                    "id": str(item.id),
                    "product_name": item.product_name,
                    "variant_sku": item.variant_sku,
                    "variant_attributes": item.variant_attributes,
                    "quantity": item.quantity,
                    "unit_price": float(item.unit_price) if item.unit_price else 0,
                    "line_total": float(item.line_total) if item.line_total else 0,
                    "created_at": item.created_at.isoformat() if item.created_at else None
                }
                for item in (order.items or [])
            ]
        }
        orders_data.append(order_dict)
    
    return {
        "orders": orders_data,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        }
    }


@router.get("/stats", response_model=dict)
def get_order_stats(
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.view")),
):
    """
    Get order statistics.
    
    Allowed:
        manager
        admin
    """
    return order_repo.get_order_statistics(session)


@router.get("/{order_id}", response_model=dict)
def get_order_detail(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.view")),
):
    """
    Get detailed order information.
    
    Allowed:
        manager
        admin
    """
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # Resolve product + first product image for each order item.
    # Order items are variant snapshots: item -> variant -> product -> images
    variant_ids = [item.variant_id for item in (order.items or [])]
    variants = (
        session.exec(
            select(ProductVariant).where(ProductVariant.id.in_(variant_ids))
        ).all()
        if variant_ids
        else []
    )
    variant_to_product = {variant.id: variant.product_id for variant in variants}
    first_images = product_image_repo.get_first_images_for_products(
        session, list(set(variant_to_product.values()))
    )
    
    items_payload = []
    for item in (order.items or []):
        product_id = variant_to_product.get(item.variant_id)
        items_payload.append({
            "id": str(item.id),
            "product_id": str(product_id) if product_id else None,
            "product_image": first_images.get(product_id),
            "product_name": item.product_name,
            "variant_sku": item.variant_sku,
            "variant_attributes": item.variant_attributes,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "line_total": float(item.line_total),
            "created_at": item.created_at.isoformat() if item.created_at else None
        })
    
    # Build response manually
    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "user_id": str(order.user_id),
        
        **order_details(order),
        
        "shipping_address_id": str(order.shipping_address_id),
        "billing_address_id": str(order.billing_address_id),
        
        # Financials
        "subtotal": float(order.subtotal),
        "discount_total": float(order.discount_total),
        "tax_total": float(order.tax_total),
        "shipping_total": float(order.shipping_total),
        "grand_total": float(order.grand_total),
        
        # Payment transaction details
        "transaction_id": order.transaction_id,
        "payment_provider": getattr(order.succeeded_payment, "provider", None) if order.succeeded_payment else None,
        "payment_method": getattr(order.succeeded_payment, "payment_method", None) if order.succeeded_payment else None,
        "paid_at": getattr(order.succeeded_payment, "paid_at", None).isoformat() if order.succeeded_payment and getattr(order.succeeded_payment, "paid_at", None) else None,
        
        # Status
        "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "cod_fee": float(order.cod_fee) if order.cod_fee is not None else 0.0,
        "coupon_code": order.coupon_code,
        
        # Cancellation
        "cancellation_reason": order.cancellation_reason,
        "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,

        # Refund position (drives the "Issue Refund" action availability)
        "refund_amount": float(order.refund_amount or 0),
        "refund_id": order.refund_id,
        "refund_reason": order.refund_reason,
        "refunded_at": order.refunded_at.isoformat() if order.refunded_at else None,
        
        # Shipping / Shiprocket
        "shiprocket_order_id": order.shiprocket_order_id,
        "shiprocket_shipment_id": order.shiprocket_shipment_id,
        "awb_code": order.awb_code,
        "courier_name": order.courier_name,
        "courier_id": order.courier_id,
        "shipping_label_url": order.shipping_label_url,
        "manifest_url": order.manifest_url,
        "shipment_status": order.shipment_status,
        "pickup_scheduled_date": order.pickup_scheduled_date.isoformat() if order.pickup_scheduled_date else None,
        "tracking_data": order.tracking_data,
        # Presentable fulfilment stage (label/step/tone) so the admin UI does not
        # have to re-derive it from raw courier strings in every screen.
        "shipment_stage": shipment_stage_payload(
            has_awb=bool(order.awb_code),
            pickup_scheduled=bool(order.pickup_scheduled_date),
            shipment_status=order.shipment_status,
            order_status=order.status.value if hasattr(order.status, "value") else order.status,
        ),

        # Timestamps
        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        
        # Items
        "items": items_payload
    }


@router.put("/{order_id}/status", response_model=OrderRead)
def update_order_status_admin(
    order_id: UUID,
    status_data: OrderStatusUpdate,
    session: SessionDep,
    current_user: User = Depends(require_perm("orders.update")),
):
    """
    Update order status.
    
    Allowed:
        manager
        admin
    """
    order = order_repo.get_order_by_id(session, order_id, for_update=True)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    old_status = order.status
    new_status = status_data.status.value

    # --- Status transition guards ---
    # Cancelled / refunded orders are TERMINAL. Never allow flipping them back
    # to an active status — that would re-enable the user-facing cancel flow
    # and cause a DOUBLE stock restore.
    if old_status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order is already {old_status.value} — its status cannot be changed",
        )

    # Forward-only fulfilment workflow (mirrors Adobe/Shopify state
    # machines): each status lists the ONLY legal next states. Free jumping
    # (e.g. pending → delivered, delivered → processing) is how orders get
    # "unknowingly" misclicked into wrong states with no audit meaning.
    # cancelled/refunded skip this check — the money-state block below
    # handles them with its pipeline-pointing message.
    _ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING: (OrderStatus.CONFIRMED,),
        OrderStatus.CONFIRMED: (OrderStatus.PROCESSING,),
        OrderStatus.PROCESSING: (OrderStatus.SHIPPED,),
        OrderStatus.SHIPPED: (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.RTO),
        OrderStatus.OUT_FOR_DELIVERY: (OrderStatus.DELIVERED, OrderStatus.RTO),
        OrderStatus.DELIVERED: (),
        OrderStatus.RTO: (),
    }
    try:
        new_status_enum = OrderStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown status: {new_status}",
        )
    if new_status_enum not in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        allowed_next = _ALLOWED_TRANSITIONS.get(old_status, ())
        if new_status_enum not in allowed_next:
            names = ", ".join(s.value for s in allowed_next) or "none — terminal"
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot move order from {old_status.value} to {new_status}. "
                    f"Allowed next: {names}."
                ),
            )

    # cancelled / refunded are MONEY states, not plain status flips: they must
    # go through the refund pipeline (ledger + PSP call + approvals), never a
    # bare status write. Use POST /admin/orders/{id}/cancel (with refund
    # choice) or POST /admin/orders/{id}/refund instead — otherwise the
    # status says "refunded" while no money moved.
    if new_status in (OrderStatus.CANCELLED.value, OrderStatus.REFUNDED.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Status '{new_status}' cannot be set directly. "
                "Use POST /admin/orders/{id}/cancel for cancellations or "
                "POST /admin/orders/{id}/refund for standalone refunds."
            ),
        )

    # Cancelling from the admin panel must behave exactly like the user-facing
    # cancel (POST /orders/{id}/cancel):
    #   * only active orders (pending / confirmed / processing) are cancellable
    #   * the reserved stock must be given back to the variants
    if new_status == OrderStatus.CANCELLED.value:
        if old_status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order cannot be cancelled. Current status: {old_status.value}",
            )
        if old_status in (OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING):
            restore_stock(session, order)

    order = order_repo.update_order_status(session, order, new_status, commit=False)
    if new_status in ("shipped", "delivered") and new_status != old_status.value:
        enqueue_order_email(session, order, f"order_{new_status}")
    session.commit()

    # --- Notifications feed ---
    # Customer gets an order_status update; admins/managers get an
    # order_cancelled alert when the cancellation happens from the panel.
    try:
        if new_status != old_status.value:
            notification_repo.notify_customer_status_changed(session, order, new_status)
        if new_status == "cancelled" and old_status != "cancelled":
            notification_repo.notify_admins_order_cancelled(session, order)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to create status notifications: {str(e)}")

    return order



# =========================================================
# SHIPROCKET / SHIPPING MANAGEMENT ENDPOINTS
# =========================================================

from fastapi.responses import HTMLResponse
from html import escape
from app.services.shiprocket_service import (
    estimate_delivery_date,
    get_shipping_service,
)
from app.schemas.order import (
    CheckServiceabilityResponse,
    AssignAWBRequest,
    ShiprocketCreateResponse,
    OrderTrackingResponse,
    SimulatorTriggerWebhookRequest,
)


@router.get("/{order_id}/shipping/serviceability", response_model=CheckServiceabilityResponse)
def check_order_shipping_serviceability(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Check courier serviceability and rates for this order's destination."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shipping_address = order.shipping_details
    if not shipping_address or not shipping_address.postal_code:
        raise HTTPException(status_code=400, detail="Order does not have a valid shipping address or postal code")

    shipping_service = get_shipping_service()
    pickup_pincode = getattr(settings, "SHIPROCKET_PICKUP_PINCODE", "110001")
    delivery_pincode = shipping_address.postal_code

    is_cod = (order.payment_method == "cod")
    couriers = shipping_service.check_serviceability(
        pickup_pincode=pickup_pincode,
        delivery_pincode=delivery_pincode,
        weight=0.5,
        cod=is_cod,
    )
    return CheckServiceabilityResponse(
        pickup_pincode=pickup_pincode,
        delivery_pincode=delivery_pincode,
        available_couriers=couriers,
    )


@router.post("/{order_id}/shipping/create", response_model=ShiprocketCreateResponse)
def create_shiprocket_order_endpoint(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Push order to Shiprocket (or simulator)."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status in (OrderStatus.CANCELLED, OrderStatus.REFUNDED):
        raise HTTPException(status_code=400, detail="Cannot ship a cancelled or refunded order")

    shipping_service = get_shipping_service()
    res = shipping_service.create_order(order)

    order.shiprocket_order_id = str(res.get("order_id"))
    order.shiprocket_shipment_id = str(res.get("shipment_id"))
    order.shipment_status = "ORDER_CREATED"
    if order.status == OrderStatus.PENDING or order.status == OrderStatus.CONFIRMED:
        order.status = OrderStatus.PROCESSING

    session.add(order)
    session.commit()
    session.refresh(order)

    return ShiprocketCreateResponse(
        order_id=order.id,
        shiprocket_order_id=order.shiprocket_order_id,
        shiprocket_shipment_id=order.shiprocket_shipment_id,
        status="ORDER_CREATED",
        message=res.get("message", "Order successfully created on Shiprocket"),
    )



@router.post("/{order_id}/shipping/assign-awb", response_model=dict)
def assign_order_awb_endpoint(
    order_id: UUID,
    data: AssignAWBRequest,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Assign courier partner and generate AWB."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.shiprocket_shipment_id:
        raise HTTPException(status_code=400, detail="Order has not been created on Shiprocket yet")

    shipping_service = get_shipping_service()
    res = shipping_service.assign_awb(order.shiprocket_shipment_id, courier_id=data.courier_id)

    order.awb_code = res.get("awb_code")
    order.courier_name = res.get("courier_name")
    order.courier_id = res.get("courier_company_id")
    # Persist the courier ETD + ETA date at the moment the courier is
    # chosen — the customer "Arriving by …" banner reads these.
    # The dispatch modal posts the selected courier's ETD along with the
    # courier_id; when absent we still store a +7-day fallback ETA so the
    # UI never shows a blank date on a shipped order.
    order.courier_etd = (data.etd or res.get("etd") or None)
    order.expected_delivery_date = estimate_delivery_date(order.courier_etd)
    order.shipment_status = "AWB_ASSIGNED"

    session.add(order)
    session.commit()
    session.refresh(order)

    return {
        "order_id": str(order.id),
        "awb_code": order.awb_code,
        "courier_name": order.courier_name,
        "courier_etd": order.courier_etd,
        "expected_delivery_date": order.expected_delivery_date.isoformat() if order.expected_delivery_date else None,
        "shipment_status": order.shipment_status,
        "message": res.get("message", "AWB successfully assigned"),
    }


@router.post("/{order_id}/shipping/request-pickup", response_model=dict)
def request_order_pickup_endpoint(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Schedule courier pickup from warehouse."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.shiprocket_shipment_id or not order.awb_code:
        raise HTTPException(status_code=400, detail="AWB must be assigned before requesting pickup")

    shipping_service = get_shipping_service()
    res = shipping_service.request_pickup(order.shiprocket_shipment_id)

    order.pickup_scheduled_date = datetime.now(timezone.utc)
    order.shipment_status = "PICKUP_SCHEDULED"

    session.add(order)
    session.commit()
    session.refresh(order)

    return {
        "order_id": str(order.id),
        "shipment_status": order.shipment_status,
        "pickup_scheduled_date": order.pickup_scheduled_date.isoformat(),
        "message": res.get("message", "Pickup requested successfully"),
    }


@router.get("/{order_id}/shipping/label", response_model=dict)
def get_order_shipping_label(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Get shipping label URL."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.shiprocket_shipment_id:
        raise HTTPException(status_code=400, detail="Shipment has not been created yet")

    shipping_service = get_shipping_service()
    res = shipping_service.generate_label(order.shiprocket_shipment_id)
    label_url = res.get("label_url")

    order.shipping_label_url = label_url
    session.add(order)
    session.commit()

    return {"label_url": label_url, "is_simulated": res.get("is_simulated", False)}



@router.get("/{order_id}/shipping/manifest", response_model=dict)
def get_order_shipping_manifest(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Get shipping manifest URL."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.shiprocket_shipment_id:
        raise HTTPException(status_code=400, detail="Shipment has not been created yet")

    shipping_service = get_shipping_service()
    res = shipping_service.generate_manifest(order.shiprocket_shipment_id)
    manifest_url = res.get("manifest_url")

    order.manifest_url = manifest_url
    session.add(order)
    session.commit()

    return {"manifest_url": manifest_url, "is_simulated": res.get("is_simulated", False)}


@router.get("/{order_id}/shipping/tracking", response_model=OrderTrackingResponse)
def get_order_shipping_tracking(
    order_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Get tracking timeline and milestone scans."""
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    scans = []
    if isinstance(order.tracking_data, list):
        scans = list(order.tracking_data)
    elif isinstance(order.tracking_data, dict) and "scans" in order.tracking_data:
        scans = list(order.tracking_data["scans"])

    # Only pull from the courier when we have no webhook scans yet, and dedupe
    # against what we already hold. Webhook scans are the source of truth: they
    # are what actually moved the order, so a poll must never contradict them.
    if order.awb_code and not scans:
        shipping_service = get_shipping_service()
        try:
            live = shipping_service.get_tracking(order.awb_code)
            sr_scans = live.get("tracking_data", {}).get("shipment_track", [])
            for s in sr_scans:
                scans.append({
                    "date": s.get("date", ""),
                    "activity": s.get("activity", ""),
                    # Shiprocket's tracking API nests location as an object;
                    # flatten it or the admin timeline renders [object Object].
                    "location": normalize_location(s.get("location")),
                    "status": s.get("sr-status-label") or s.get("status", ""),
                })
        except Exception:
            pass

    stage = shipment_stage_payload(
        has_awb=bool(order.awb_code),
        pickup_scheduled=bool(order.pickup_scheduled_date),
        shipment_status=order.shipment_status,
        order_status=order.status.value if hasattr(order.status, "value") else order.status,
    )

    return OrderTrackingResponse(
        order_id=order.id,
        order_number=order.order_number,
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        # Human label ("Pickup Scheduled"), not the raw courier token
        # ("PICKUP_SCHEDULED") — the raw value is kept in raw_status.
        current_status=stage["label"],
        raw_status=stage["raw_status"],
        stage=stage,
        # Shiprocket's tracking API does not return a reliable ETA, so this is
        # None rather than a fabricated promise we cannot keep. The UI hides the
        # field entirely when absent.
        etd=None,
        scans=scans,
        tracking_url=f"https://shiprocket.co/tracking/{order.awb_code}" if order.awb_code else None,
    )



# --- Visual Simulator Printable Label & Manifest HTML helpers ---

@router.get("/shipping/simulated-label/{shipment_id}")
def view_simulated_label(shipment_id: str, session: SessionDep,
                         current_user: User = Depends(require_perm("shipping.manage"))):
    """Returns a printable mock Shiprocket Shipping Label in HTML/CSS."""
    statement = select(Order).where(Order.shiprocket_shipment_id == shipment_id)
    order = session.execute(statement).scalars().first()
    if not order:
        return HTMLResponse("<h3>Shipment not found</h3>", status_code=404)

    shipping = order.shipping_details
    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Shipping Label - {escape(str(order.awb_code or shipment_id))}</title>
        <style>
            body {{ font-family: monospace, sans-serif; margin: 20px; }}
            .label-box {{ width: 380px; border: 2px solid #000; padding: 15px; margin: auto; }}
            .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 8px; }}
            .barcode {{ text-align: center; margin: 15px 0; font-family: monospace; font-size: 22px; letter-spacing: 5px; }}
            .section {{ border-bottom: 1px solid #000; padding: 8px 0; font-size: 13px; }}
            .bold {{ font-weight: bold; }}
            @media print {{ body {{ margin: 0; }} .no-print {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="no-print" style="text-align: center; margin-bottom: 15px;">
            <button onclick="window.print()" style="padding: 8px 16px; cursor: pointer; font-weight: bold;">🖨️ Print Shipping Label</button>
        </div>
        <div class="label-box">
            <div class="header">
                <div>
                    <span class="bold">SHIPROCKET</span> (SIMULATOR)<br/>
                    <span>{escape(str(order.courier_name or 'DELHIVERY'))}</span>
                </div>
                <div style="text-align: right;">
                    <span class="bold">{escape('COD: ' + format_money(order.grand_total) if order.payment_method == 'cod' else 'PREPAID')}</span>
                </div>
            </div>
            <div class="barcode">
                |||||| | |||||||| |||| | ||||||<br/>
                <span style="font-size: 14px; letter-spacing: 2px;">{escape(str(order.awb_code or 'SR-AWB-998877'))}</span>
            </div>
            <div class="section">
                <span class="bold">Ship To:</span><br/>
                {escape(str(order.customer_details.full_name or 'Customer') if order.customer_details else 'Customer')}<br/>
                {escape(str(shipping.line1 or '') if shipping else '')}<br/>
                {escape(str(shipping.city or '') if shipping else '')}, {escape(str(shipping.state or '') if shipping else '')} - <span class="bold">{escape(str(shipping.postal_code or '') if shipping else '')}</span><br/>
                Phone: {escape(str(order.customer_details.phone) if order.customer_details and order.customer_details.phone else 'N/A')}
            </div>
            <div class="section">
                <span class="bold">Order No:</span> {escape(str(order.order_number))}<br/>
                <span class="bold">Date:</span> {order.placed_at.strftime('%d-%b-%Y')}<br/>
                <span class="bold">Dimensions:</span> 10x10x10 cm | 0.50 kg
            </div>
            <div style="font-size: 11px; margin-top: 10px; color: #555; text-align: center;">
                Return Address: Warehouse Primary Hub, Industrial Area, New Delhi - 110001
            </div>
        </div>
    </body>
    </html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})



@router.get("/shipping/simulated-manifest/{shipment_id}")
def view_simulated_manifest(shipment_id: str, session: SessionDep,
                            current_user: User = Depends(require_perm("shipping.manage"))):
    """Returns a printable mock Shiprocket Pickup Manifest in HTML/CSS."""
    statement = select(Order).where(Order.shiprocket_shipment_id == shipment_id)
    order = session.execute(statement).scalars().first()
    if not order:
        return HTMLResponse("<h3>Shipment not found</h3>", status_code=404)

    html = f"""<!DOCTYPE html>
    <html>
    <head>
        <title>Pickup Manifest - {escape(shipment_id)}</title>
        <style>
            body {{ font-family: sans-serif; margin: 30px; font-size: 13px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ border: 1px solid #333; padding: 8px; text-align: left; }}
            th {{ background: #eee; }}
            .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 10px; }}
            @media print {{ .no-print {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="no-print" style="margin-bottom: 15px;">
            <button onclick="window.print()" style="padding: 8px 16px; cursor: pointer; font-weight: bold;">🖨️ Print Manifest</button>
        </div>
        <div class="header">
            <div>
                <h2>SHIPROCKET COURIER MANIFEST</h2>
                <p>Courier Partner: <b>{escape(str(order.courier_name or 'Delhivery'))}</b></p>
            </div>
            <div style="text-align: right;">
                <p>Date: <b>{datetime.now().strftime('%d-%m-%Y')}</b></p>
                <p>Manifest ID: <b>MNF-{escape(shipment_id)}</b></p>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>AWB Number</th>
                    <th>Order Number</th>
                    <th>Destination Pincode</th>
                    <th>Payment</th>
                    <th>Weight</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>1</td>
                    <td><b>{escape(str(order.awb_code or 'N/A'))}</b></td>
                    <td>{escape(str(order.order_number))}</td>
                    <td>{escape(str(order.shipping_details.postal_code or '') if order.shipping_details else 'N/A')}</td>
                    <td>{escape('COD (' + format_money(order.grand_total) + ')' if order.payment_method == 'cod' else 'PREPAID')}</td>
                    <td>0.50 kg</td>
                </tr>
            </tbody>
        </table>
        <div style="margin-top: 50px; display: flex; justify-content: space-between;">
            <div>__________________________<br/>Merchant Signature</div>
            <div>__________________________<br/>Courier Executive Signature</div>
        </div>
    </body>
    </html>"""
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})



# =========================================================
# SIMULATOR TAB ENDPOINTS (ADMIN TOOLS)
# =========================================================

@router.get("/shipping/simulator/shipments", response_model=dict)
def get_simulator_shipments(
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """Retrieve all orders that have shipment records for the Simulator Control Panel."""
    statement = (
        select(Order)
        .where(Order.shiprocket_order_id.is_not(None))
        .order_by(Order.updated_at.desc())
        .options(
            selectinload(Order.user),
            selectinload(Order.shipping_address),
        )
    )
    orders = session.execute(statement).scalars().all()
    results = []
    for o in orders:
        results.append({
            "order_id": str(o.id),
            "order_number": o.order_number,
            "user_name": o.customer_details.full_name if o.customer_details else "Customer",
            "shiprocket_order_id": o.shiprocket_order_id,
            "shiprocket_shipment_id": o.shiprocket_shipment_id,
            "awb_code": o.awb_code,
            "courier_name": o.courier_name,
            "order_status": o.status.value,
            "payment_status": o.payment_status,
            "shipment_status": o.shipment_status,
            "shipment_stage": shipment_stage_payload(
                has_awb=bool(o.awb_code),
                pickup_scheduled=bool(o.pickup_scheduled_date),
                shipment_status=o.shipment_status,
                order_status=o.status.value if hasattr(o.status, "value") else o.status,
            ),
            "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            "tracking_scans_count": len(o.tracking_data) if isinstance(o.tracking_data, list) else 0,
        })
    return {"shipments": results, "count": len(results), "provider": getattr(settings, "SHIPPING_PROVIDER", "simulator")}


#: Simulator event name -> the real Shiprocket ``current_status`` it emits.
#: Keys are the friendly names the admin UI sends; values are what Shiprocket
#: would actually POST. Keeping this table explicit (rather than upper-casing the
#: event name) is what makes the simulator emit genuine courier statuses —
#: including the tricky ones like "RTO IN TRANSIT" that a naive mapping gets
#: wrong.
SIMULATOR_EVENTS: dict[str, str] = {
    # Pre-pickup paperwork — order stays "processing".
    "awaiting_pickup": "AWAITING PICKUP SCHEDULE",
    "label_generated": "LABEL GENERATED",
    "manifest_generated": "MANIFEST GENERATED",
    "pickup_scheduled": "PICKUP SCHEDULED",
    "pickup_attempted": "PICKUP ATTEMPTED",
    # The parcel has physically left the warehouse -> shipped.
    "picked_up": "PICKED UP",
    "in_transit": "IN TRANSIT",
    "shipped": "IN TRANSIT",
    "dispatched": "DISPATCHED",
    # Last mile.
    "out_for_delivery": "OUT FOR DELIVERY",
    "appointment_booked": "CUSTOMER APPOINTMENT BOOKED",
    "delivered": "DELIVERED",
    # Delivery failure/NDR precedes an RTO decision in the real flow.
    "delivery_failed": "UNDELIVERED",
    "undelivered": "UNDELIVERED",
    # Return to origin is a branch of the ORIGINAL forward shipment. It must
    # stay in the outbound card and never be marked is_return=1.
    "rto_initiated": "RTO INITIATED",
    "rto_in_transit": "RTO IN TRANSIT",
    "rto_dispatched": "RTO DISPATCHED",
    "rto_ofd": "RTO OFD",
    "rto": "RTO IN TRANSIT",
    "rto_delivered": "RTO DELIVERED",
    "rto_acknowledged": "RTO ACKNOWLEDGED",
    # Exceptions: recorded on the timeline, order status untouched.
    "noc": "NOC",
    "exception": "NOC",
    "lost": "LOST",
    "damaged": "DAMAGED",
    "missorted": "3PL MISSORT",
    "on_hold": "ON HOLD",
}


@router.post("/{order_id}/shipping/simulator/trigger-event", response_model=dict)
def trigger_simulator_event(
    order_id: UUID,
    data: SimulatorTriggerWebhookRequest,
    session: SessionDep,
    current_user: User = Depends(require_perm("shipping.manage")),
):
    """
    Simulate a Shiprocket tracking webhook hitting the backend.

    Builds a payload in Shiprocket's real wire format (top-level ``data`` key,
    numeric ``shipment_status``, boolean flags) and feeds it through
    ``process_tracking_event`` — the exact function the public
    ``/webhooks/shiprocket`` endpoint calls.

    That shared path is the whole point: the simulator cannot pass while
    production would fail. If Shiprocket changes its payload shape, the simulator
    breaks immediately instead of live shipments going silently missing.
    """
    order = order_repo.get_order_by_id(session, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if not order.awb_code:
        raise HTTPException(
            status_code=400, detail="Shipment does not have an AWB assigned yet"
        )

    event_type = data.event.strip().lower()
    shiprocket_status = SIMULATOR_EVENTS.get(event_type)
    if shiprocket_status is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown simulator event '{data.event}'. Valid events: "
                + ", ".join(sorted(SIMULATOR_EVENTS))
            ),
        )

    before = simulation_state(order)
    payload = build_tracking_webhook_payload(
        awb=order.awb_code,
        current_status=shiprocket_status,
        location=data.location or "Regional Processing Hub",
        activity=data.activity or f"Shipment status: {shiprocket_status}",
        order_id=order.id.int if hasattr(order.id, "int") else None,
        # RTO is Return-to-Origin for the original shipment, not a customer
        # return order. Customer reverse shipments use the separate return
        # simulator endpoint and is_return=1.
        is_return=0,
    )

    result = process_tracking_event(session, payload)
    session.refresh(order)
    after = simulation_state(order)

    return {
        "success": True,
        "order_id": str(order.id),
        "event_triggered": event_type,
        "shiprocket_status": shiprocket_status,
        # The exact body Shiprocket would POST — surfaced in the admin UI so the
        # wire format is inspectable, not just assumed.
        "simulated_payload": payload,
        "order_status": order.status.value,
        "shipment_status": order.shipment_status,
        "payment_status": order.payment_status,
        "status_changed": result.get("status_changed", False),
        "before": before,
        "after": after,
        "effects": {
            "order_status_changed": before["order_status"] != after["order_status"],
            "shipment_status_changed": before["shipment_status"] != after["shipment_status"],
            "rto_started": before["order_status"] != "rto" and after["order_status"] == "rto",
            "rto_stock_restored_now": not before["rto_stock_restored"] and after["rto_stock_restored"],
            "money_changed": before["payment_status"] != after["payment_status"] or before["refund_amount"] != after["refund_amount"],
            "forward_awb_preserved": before["forward_awb"] == after["forward_awb"],
        },
    }
