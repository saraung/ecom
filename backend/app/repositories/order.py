from datetime import datetime, timedelta, timezone
from datetime import date
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel import Session

from app.models.order import Order, OrderItem, OrderStatus
from app.models.user import User
from app.models.address import Address  # Add this if you have address model
from app.models.product import Product, ProductVariant  # ⚠️ ASSUMED — see note below
from app.repositories.commerce import settled_sale, net_sale_amount


# Eager-load chain used by the user-facing order responses: each order item
# resolves its product slug + first image via item -> variant -> product -> images
_ORDER_ITEM_PRODUCT_LOAD = (
    selectinload(Order.items)
    .selectinload(OrderItem.variant)
    .selectinload(ProductVariant.product)
    .selectinload(Product.images)
)


def get_order_by_id(session: Session, order_id: UUID, *, for_update: bool = False) -> Order | None:
    """Get order by ID with items and user loaded"""
    statement = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            _ORDER_ITEM_PRODUCT_LOAD,
            selectinload(Order.user),  # 👈 Add this
            selectinload(Order.shipping_address),  # 👈 Add this
            selectinload(Order.billing_address),   # 👈 Add this
            selectinload(Order.payments),  # 👈 resolves transaction_id
        )
    )
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_orders_by_user(
    session: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> list[Order]:
    """Get all orders for a user"""
    statement = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .options(
            _ORDER_ITEM_PRODUCT_LOAD,
            selectinload(Order.shipping_address),
            selectinload(Order.payments),  # 👈 resolves transaction_id
        )
    )
    result = session.execute(statement)
    return result.scalars().all()


def get_order_by_refund_id(session: Session, refund_id: str) -> Order | None:
    """Get order by the stored Razorpay refund ID (rfnd_xxx).

    Uses .first() (most recent order) instead of scalar_one_or_none() so a
    duplicate refund_id in the DB can never crash the webhook handler.
    """
    statement = (
        select(Order)
        .where(Order.refund_id == refund_id)
        .order_by(Order.placed_at.desc())
        .options(
            selectinload(Order.items),
            selectinload(Order.user),
            selectinload(Order.shipping_address),
        )
    )
    result = session.execute(statement)
    return result.scalars().first()


def get_order_by_number(session: Session, order_number: str) -> Order | None:
    """Get order by order number"""
    statement = (
        select(Order)
        .where(Order.order_number == order_number)
        .options(
            _ORDER_ITEM_PRODUCT_LOAD,
            selectinload(Order.user),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),  # 👈 resolves transaction_id
        )
    )
    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_order_by_awb(session: Session, awb_code: str) -> Order | None:
    """Get order by AWB code"""
    statement = (
        select(Order)
        .where(Order.awb_code == awb_code)
        .options(
            _ORDER_ITEM_PRODUCT_LOAD,
            selectinload(Order.user),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),
        )
    )
    result = session.execute(statement)
    return result.scalars().first()


def get_order_by_shiprocket_order_id(session: Session, sr_order_id: str) -> Order | None:
    """Get order by Shiprocket Order ID"""
    statement = (
        select(Order)
        .where(Order.shiprocket_order_id == sr_order_id)
        .options(
            _ORDER_ITEM_PRODUCT_LOAD,
            selectinload(Order.user),
            selectinload(Order.shipping_address),
            selectinload(Order.payments),
        )
    )
    result = session.execute(statement)
    return result.scalars().first()


def get_verified_purchase_order_id(
    session: Session,
    user_id: UUID,
    product_id: UUID,
) -> UUID | None:
    """
    Return the id of the most recent order where this user purchased
    and received this product (order delivered), or None if no such
    order exists. Used to gate review creation to verified purchases.

    OrderItem stores variant_id (not product_id), so this joins through
    ProductVariant to match on the parent product.
    """
    statement = (
        select(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(ProductVariant, ProductVariant.id == OrderItem.variant_id)
        .where(
            Order.user_id == user_id,
            ProductVariant.product_id == product_id,
            Order.status == OrderStatus.DELIVERED,
        )
        .order_by(Order.placed_at.desc())
    )
    row = session.execute(statement).first()
    return row[0] if row else None


def get_all_orders(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
) -> list[Order]:
    """Get all orders (admin)"""
    statement = select(Order).options(
        selectinload(Order.items),
        selectinload(Order.user),  # 👈 Add this
        selectinload(Order.shipping_address),  # 👈 Add this
    )
    
    if status:
        statement = statement.where(Order.status == status)
    
    statement = statement.order_by(Order.placed_at.desc())
    statement = statement.offset(skip).limit(limit)
    
    result = session.execute(statement)
    return result.scalars().all()


def update_order_status(
    session: Session,
    order: Order,
    status: str,
    *, commit: bool = True,
) -> Order:
    """Update order status"""
    order.status = status
    
    # Auto-update timestamps
    if status == "shipped":
        order.shipped_at = datetime.now(timezone.utc)
    elif status == "delivered":
        order.delivered_at = datetime.now(timezone.utc)
    
    session.add(order)
    if commit:
        session.commit()
        session.refresh(order)
    else:
        session.flush()
    return order


# =========================================================
# ADMIN FUNCTIONS
# =========================================================

def get_order_statistics(session: Session) -> dict:
    """Get order statistics"""
    total_orders = session.execute(select(func.count()).select_from(Order)).scalar() or 0
    
    pending_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.PENDING)
    ).scalar() or 0
    
    confirmed_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.CONFIRMED)
    ).scalar() or 0
    
    shipped_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.SHIPPED)
    ).scalar() or 0
    
    delivered_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.DELIVERED)
    ).scalar() or 0
    
    cancelled_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.CANCELLED)
    ).scalar() or 0
    
    refunded_orders = session.execute(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.REFUNDED)
    ).scalar() or 0
    
    return {
        "total": total_orders,
        "pending": pending_orders,
        "confirmed": confirmed_orders,
        "shipped": shipped_orders,
        "delivered": delivered_orders,
        "cancelled": cancelled_orders,
        "refunded": refunded_orders,
    }


def get_user_order_statistics(session: Session, user_id: UUID) -> dict:
    """
    Get lifetime order statistics for a single user (admin view).

    Returns:
        dict: total_orders, total_spent, gross_total, refunded_total,
            average_order_value, total_items_purchased, first_order,
            last_order, per-status breakdown, most_ordered_product
    """
    total_orders = (
        session.execute(
            select(func.count()).select_from(Order).where(Order.user_id == user_id)
        ).scalar()
        or 0
    )

    # Settled active commerce, matching financial reports.
    total_spent = (
        session.execute(
            select(func.coalesce(func.sum(net_sale_amount()), 0))
            .select_from(Order)
            .where(
                Order.user_id == user_id,
                settled_sale(),
            )
        ).scalar()
        or 0
    )

    # Gross total = sum of grand_total across EVERY order (incl. cancelled / refunded)
    gross_total = (
        session.execute(
            select(func.coalesce(func.sum(Order.grand_total), 0))
            .select_from(Order)
            .where(Order.user_id == user_id)
        ).scalar()
        or 0
    )

    # Total refunded so far
    refunded_total = (
        session.execute(
            select(func.coalesce(func.sum(Order.refund_amount), 0))
            .select_from(Order)
            .where(Order.user_id == user_id)
        ).scalar()
        or 0
    )

    # First / last order timestamps
    first_order = session.execute(
        select(Order.placed_at)
        .where(Order.user_id == user_id)
        .order_by(Order.placed_at.asc())
        .limit(1)
    ).scalar()
    last_order = session.execute(
        select(Order.placed_at)
        .where(Order.user_id == user_id)
        .order_by(Order.placed_at.desc())
        .limit(1)
    ).scalar()

    # Only retained purchases contribute units and the favorite-product metric.
    total_items_purchased = (
        session.execute(
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .where(Order.user_id == user_id, settled_sale())
        ).scalar()
        or 0
    )

    # Per-status counts
    status_counts = {}
    for status in OrderStatus:
        status_counts[status.value] = (
            session.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.user_id == user_id, Order.status == status)
            ).scalar()
            or 0
        )

    # Most-purchased product (grouped by the order-item snapshot name)
    most_ordered = session.execute(
        select(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty"))
        .select_from(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.user_id == user_id, settled_sale())
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc(), OrderItem.product_name.asc())
        .limit(1)
    ).first()

    settled_orders = session.execute(select(func.count(Order.id)).where(
        Order.user_id == user_id, settled_sale())).scalar() or 0
    average_order_value = float(total_spent) / settled_orders if settled_orders else 0

    return {
        "total_orders": total_orders,
        "total_spent": float(total_spent),
        "gross_total": float(gross_total),
        "refunded_total": float(refunded_total),
        "average_order_value": round(average_order_value, 2),
        "total_items_purchased": total_items_purchased,
        "first_order": first_order.isoformat() if first_order else None,
        "last_order": last_order.isoformat() if last_order else None,
        "status_breakdown": status_counts,
        "most_ordered_product": most_ordered[0] if most_ordered else None,
    }


def get_recent_orders(session: Session, limit: int = 10) -> list[Order]:
    """Get recent orders with user data"""
    statement = (
        select(Order)
        .order_by(Order.placed_at.desc())
        .limit(limit)
        .options(
            selectinload(Order.user),  # 👈 Add this
            selectinload(Order.shipping_address),  # 👈 Add this
            selectinload(Order.items),  # 👈 Add this
        )
    )
    result = session.execute(statement)
    return result.scalars().all()


def get_all_orders_with_filters(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    payment_status: str | None = None,
) -> tuple[list[Order], int]:
    """Get all orders with filters and user data"""
    # Build base query with eager loading
    statement = select(Order).options(
        selectinload(Order.items),  # 👈 Keep this
        selectinload(Order.user),  # 👈 ADD THIS - loads user data
        selectinload(Order.shipping_address),  # 👈 ADD THIS - loads shipping address
        selectinload(Order.billing_address),   # 👈 ADD THIS - loads billing address
    )
    
    # Apply filters
    if status:
        statement = statement.where(Order.status == status)

    if payment_status:
        statement = statement.where(Order.payment_status == payment_status)
    
    if search:
        # Search by order number or customer name/email
        statement = statement.where(
            (Order.order_number.ilike(f"%{search}%")) |
            (Order.user.has(User.full_name.ilike(f"%{search}%"))) |
            (Order.user.has(User.email.ilike(f"%{search}%")))
        )
    
    if from_date:
        statement = statement.where(Order.placed_at >= from_date)
    
    if to_date:
        statement = statement.where(Order.placed_at <= to_date)
    
    # Get total count
    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.execute(count_statement).scalar() or 0
    
    # Get paginated results
    statement = statement.order_by(Order.placed_at.desc()).offset(skip).limit(limit)
    result = session.execute(statement)
    orders = result.scalars().all()
    
    return orders, total


def get_order_summary(session: Session) -> dict:
    """Get order summary for admin dashboard"""
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    # Today's orders
    today_orders = session.execute(
        select(func.count(Order.id)).where(func.date(Order.placed_at) == today)
    ).scalar() or 0
    
    # This week's orders
    week_orders = session.execute(
        select(func.count(Order.id)).where(Order.placed_at >= start_of_week)
    ).scalar() or 0
    
    # This month's orders
    month_orders = session.execute(
        select(func.count(Order.id)).where(Order.placed_at >= start_of_month)
    ).scalar() or 0
    
    return {
        "today": today_orders,
        "this_week": week_orders,
        "this_month": month_orders,
    }
