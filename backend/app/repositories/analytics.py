from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, case
from sqlmodel import Session, select, col

from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductVariant, ProductImage  # 👈 ADD ProductVariant IMPORT
from app.models.user import User
from app.repositories.commerce import settled_sale, net_sale_amount, date_filters


def _period_column(session, group_by):
    if group_by == "day":
        return func.date(Order.placed_at)
    if session.get_bind().dialect.name == "sqlite":
        if group_by == "month":
            return func.strftime('%Y-%m-01', Order.placed_at)
        return func.date(Order.placed_at, '-6 days', 'weekday 1')
    return func.date_trunc(group_by, Order.placed_at)


def get_sales_report(
    session: Session,
    from_date: date,
    to_date: date,
    group_by: str = "day",
) -> dict:
    """
    Get sales report grouped by day, week, or month.
    """
    # Base query
    statement = select(
        func.sum(net_sale_amount()).label("total_sales"),
        func.count(Order.id).label("order_count"),
        func.avg(net_sale_amount()).label("average_order_value"),
    ).where(
        *date_filters(Order.placed_at, from_date, to_date),
        settled_sale(),
    )
    
    result = session.exec(statement).first()
    
    # Group by period
    group_col = _period_column(session, group_by)
    
    statement = select(
        group_col.label("period"),
        func.sum(net_sale_amount()).label("total_sales"),
        func.count(Order.id).label("order_count"),
        func.avg(net_sale_amount()).label("average_order_value"),
    ).where(
        *date_filters(Order.placed_at, from_date, to_date),
        settled_sale(),
    ).group_by(group_col).order_by(group_col)
    
    period_data = session.exec(statement).all()
    
    return {
        "summary": {
            "total_sales": float(result[0] or 0),
            "order_count": result[1] or 0,
            "average_order_value": float(result[2] or 0),
        },
        "period_data": [
            {
                "period": str(row[0]),
                "total_sales": float(row[1] or 0),
                "order_count": row[2] or 0,
                "average_order_value": float(row[3] or 0),
            }
            for row in period_data
        ]
    }


def get_sales_trend(session: Session, days: int = 7) -> list[dict]:
    """
    Get daily sales + order counts for the last `days` days, zero-filled.

    Aggregates REAL order data grouped by calendar day using proper datetime
    bounds (midnight → next midnight) so today's orders are always included.

    Returns:
        list[dict]: [{ "date": "YYYY-MM-DD", "sales": float, "orders": int }, ...]
    """
    today = datetime.now(timezone.utc).date()
    from_date = today - timedelta(days=max(days - 1, 0))

    statement = (
        select(
            func.date(Order.placed_at).label("period"),
            func.coalesce(func.sum(net_sale_amount()), 0).label("total_sales"),
            func.count(Order.id).label("order_count"),
        )
        .where(
            *date_filters(Order.placed_at, from_date, today),
            settled_sale(),
        )
        .group_by("period")
    )

    by_period = {
        str(row.period): {"sales": float(row.total_sales or 0), "orders": row.order_count or 0}
        for row in session.exec(statement).all()
    }

    trend = []
    for i in range(days):
        iso = (from_date + timedelta(days=i)).isoformat()
        day_stats = by_period.get(iso, {"sales": 0.0, "orders": 0})
        trend.append(
            {
                "date": iso,
                "sales": day_stats["sales"],
                "orders": day_stats["orders"],
            }
        )
    return trend


def get_top_products(
    session: Session,
    limit: int = 10,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """
    Get top selling products.
    """
    item_totals = select(OrderItem.order_id, func.sum(OrderItem.line_total).label("total")) \
        .group_by(OrderItem.order_id).subquery()
    discounted = item_totals.c.total - Order.discount_total
    discount_ratio = case((discounted > 0, discounted / func.nullif(item_totals.c.total, 0)), else_=0)
    refund_ratio = net_sale_amount() / func.nullif(Order.grand_total, 0)
    merchandise_revenue = OrderItem.line_total * discount_ratio * refund_ratio
    statement = (
        select(
            Product.id,
            Product.name,
            Product.slug,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("total_quantity_sold"),
            func.coalesce(func.sum(merchandise_revenue), 0).label("total_revenue"),
            func.coalesce(func.sum(merchandise_revenue) / func.nullif(func.sum(OrderItem.quantity), 0), 0).label("average_price"),
            func.count(Order.id.distinct()).label("order_count"),
            func.count(ProductVariant.id.distinct()).label("variant_count"),
        )
        .select_from(Product)  # 👈 IMPORTANT: This establishes the base table
        .join(ProductVariant, Product.id == ProductVariant.product_id)  # 👈 Now ProductVariant is imported
        .join(OrderItem, ProductVariant.id == OrderItem.variant_id)
        .join(Order, OrderItem.order_id == Order.id)
        .join(item_totals, item_totals.c.order_id == Order.id)
    )
    
    statement = statement.where(
        *date_filters(Order.placed_at, from_date, to_date), settled_sale(),
    ).group_by(Product.id, Product.name, Product.slug)
    
    statement = statement.order_by(
        func.sum(merchandise_revenue).desc(),
        func.sum(OrderItem.quantity).desc()
    ).limit(limit)
    
    results = session.exec(statement).all()
    
    print(f"DEBUG: Found {len(results)} top products")
    
    return [
        {
            "product_id": str(row[0]),
            "product_name": row[1],
            "product_slug": row[2],
            "total_quantity_sold": int(row[3] or 0),
            "total_revenue": float(row[4] or 0),
            "average_price": float(row[5] or 0),
            "order_count": int(row[6] or 0),
            "variant_count": int(row[7] or 0),
        }
        for row in results
    ]


def get_dashboard_top_products(
    session: Session, limit: int = 10, days: int = 30
) -> list[dict]:
    """Top products by revenue for the admin dashboard chart (last `days` days).

    Reuses :func:`get_top_products` (which aggregates order_items through their
    variant so cancelled/refunded orders are already excluded) and reshapes the rows into the compact form the dashboard widget
    consumes in ``revenue.top_products``:

        [{ "product_id", "product_name", "revenue", "units_sold", "image_url" }, ...]

    ``image_url`` is the product's primary image (lowest ``sort_order``) resolved
    with ONE extra query, so the widget can show thumbnails without firing a
    request per row. It is None when the product has no images yet.

    Returns an empty list when nothing sold in the window — the caller then
    falls back to the period-over-period chart.
    """
    to_date = datetime.now(timezone.utc).date()
    from_date = to_date - timedelta(days=max(days - 1, 0))

    rows = get_top_products(
        session, limit=limit, from_date=from_date, to_date=to_date
    )
    if not rows:
        return []

    # Resolve every primary image in a single ordered query; the first row seen
    # for a product wins (lowest sort_order = the image admins marked as main).
    primary_images: dict[str, str] = {}
    for image in session.exec(
        select(ProductImage)
        .where(col(ProductImage.product_id).in_([UUID(row["product_id"]) for row in rows]))
        .order_by(col(ProductImage.sort_order))
    ).all():
        primary_images.setdefault(str(image.product_id), image.url)

    return [
        {
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "revenue": row["total_revenue"],
            "units_sold": row["total_quantity_sold"],
            "image_url": primary_images.get(row["product_id"]),
        }
        for row in rows
    ]


def get_order_statistics(
    session: Session,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Get order statistics by status.
    """
    status_counts = {}
    total_revenue_by_status = {}
    
    for status in OrderStatus:
        statement = select(
            func.count(Order.id),
            func.sum(case((settled_sale(), net_sale_amount()), else_=0)),
        ).where(Order.status == status, *date_filters(Order.placed_at, from_date, to_date))
        
        result = session.exec(statement).first()
        status_counts[status.value] = result[0] or 0
        total_revenue_by_status[status.value] = float(result[1] or 0)
    
    # Total orders
    total_statement = select(func.count(Order.id)).where(*date_filters(Order.placed_at, from_date, to_date))
    total_orders = session.exec(total_statement).first() or 0
    
    return {
        "total_orders": total_orders,
        "by_status": [
            {
                "status": status,
                "count": status_counts.get(status, 0),
                "revenue": total_revenue_by_status.get(status, 0),
            }
            for status in status_counts.keys()
        ]
    }


def get_revenue_report(
    session: Session,
    from_date: date,
    to_date: date,
    group_by: str = "day",
) -> dict:
    """
    Get revenue report.
    """
    # Define group_col based on group_by
    group_col = _period_column(session, group_by)
    
    statement = select(
        group_col.label("period"),
        func.sum(Order.grand_total).label("revenue"),
        func.sum(Order.discount_total).label("discounts"),
        func.sum(Order.tax_total).label("tax"),
        func.sum(Order.shipping_total).label("shipping"),
        func.sum(net_sale_amount()).label("net_revenue"),
        func.sum(Order.refund_amount).label("refunds"),
    ).where(
        *date_filters(Order.placed_at, from_date, to_date), settled_sale(),
    ).group_by(group_col).order_by(group_col)
    
    results = session.exec(statement).all()
    
    return {
        "period_data": [
            {
                "period": str(row[0]),
                "revenue": float(row[1] or 0),
                "discounts": float(row[2] or 0),
                "tax": float(row[3] or 0),
                "shipping": float(row[4] or 0),
                # grand_total already includes the discount; deduct refunds only.
                "net_revenue": float(row[5] or 0),
                "refunds": float(row[6] or 0),
            }
            for row in results
        ]
    }


def get_customer_summary(
    session: Session,
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict:
    """
    Get customer analytics summary.
    """
    # Total customers
    total_customers = session.exec(select(func.count(User.id))).first() or 0
    
    # Active customers (placed order in period)
    statement = select(func.count(User.id.distinct())).select_from(Order).join(
        User, Order.user_id == User.id
    ).where(settled_sale(), *date_filters(Order.placed_at, from_date, to_date))
    
    active_customers = session.exec(statement).first() or 0
    
    # New customers (registered in period)
    statement = select(func.count(User.id)).where(*date_filters(User.created_at, from_date, to_date))
    new_customers = session.exec(statement).first() or 0
    
    # Repeat customers
    statement = select(
        Order.user_id, func.count(Order.id).label("order_count"),
    ).where(settled_sale(), *date_filters(Order.placed_at, from_date, to_date)) \
        .group_by(Order.user_id).having(func.count(Order.id) > 1)
    repeat_customers = len(session.exec(statement).all())
    
    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "new_customers": new_customers,
        "repeat_customers": repeat_customers,
        "customer_retention_rate": round(
            (repeat_customers / active_customers * 100) if active_customers > 0 else 0, 2
        ),
    }


def get_dashboard_stats(
    session: Session,
) -> dict:
    """
    Get dashboard statistics for admin.
    """
    today = datetime.now(timezone.utc).date()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    
    # Today's stats
    today_orders = session.exec(
        select(func.count(Order.id)).where(func.date(Order.placed_at) == today)
    ).first() or 0
    
    today_revenue = session.exec(
        select(func.sum(net_sale_amount())).where(
            *date_filters(Order.placed_at, today, today), settled_sale(),
        )
    ).first() or Decimal("0.00")
    
    # This week's stats
    week_orders = session.exec(
        select(func.count(Order.id)).where(*date_filters(Order.placed_at, start_of_week, today))
    ).first() or 0
    
    week_revenue = session.exec(
        select(func.sum(net_sale_amount())).where(
            *date_filters(Order.placed_at, start_of_week, today), settled_sale(),
        )
    ).first() or Decimal("0.00")
    
    # This month's stats
    month_orders = session.exec(
        select(func.count(Order.id)).where(*date_filters(Order.placed_at, start_of_month, today))
    ).first() or 0
    
    month_revenue = session.exec(
        select(func.sum(net_sale_amount())).where(
            *date_filters(Order.placed_at, start_of_month, today), settled_sale(),
        )
    ).first() or Decimal("0.00")
    
    # Total orders
    total_orders = session.exec(
        select(func.count(Order.id))
    ).first() or 0
    
    total_revenue = session.exec(
        select(func.sum(net_sale_amount())).where(settled_sale())
    ).first() or Decimal("0.00")
    
    # Pending orders
    pending_orders = session.exec(
        select(func.count(Order.id)).where(Order.status == OrderStatus.PENDING)
    ).first() or 0
    
    # Total products
    total_products = session.exec(select(func.count(Product.id))).first() or 0
    
    return {
        "today": {
            "orders": today_orders,
            "revenue": float(today_revenue),
        },
        "this_week": {
            "orders": week_orders,
            "revenue": float(week_revenue),
        },
        "this_month": {
            "orders": month_orders,
            "revenue": float(month_revenue),
        },
        "total": {
            "orders": total_orders,
            "revenue": float(total_revenue),
            "pending_orders": pending_orders,
            "total_products": total_products,
        },
    }


def revenue_totals(
    session: Session,
    from_date: date,
    to_date: date,
) -> dict:
    """Single-row revenue totals (same scope as get_revenue_report)."""
    row = session.exec(
        select(
            func.sum(net_sale_amount()).label("net_revenue"),
            func.sum(Order.grand_total).label("gross"),
            func.sum(Order.discount_total).label("discounts"),
            func.sum(Order.tax_total).label("tax"),
            func.sum(Order.shipping_total).label("shipping"),
            func.sum(Order.refund_amount).label("refunds"),
            func.count(Order.id).label("orders"),
        ).where(
            *date_filters(Order.placed_at, from_date, to_date), settled_sale(),
        )
    ).first()
    return {
        "net_revenue": float(row[0] or 0),
        "gross": float(row[1] or 0),
        "discounts": float(row[2] or 0),
        "tax": float(row[3] or 0),
        "shipping": float(row[4] or 0),
        "refunds": float(row[5] or 0),
        "orders": row[6] or 0,
    }


def payment_status_summary(
    session: Session,
    from_date: date,
    to_date: date,
) -> list[dict]:
    """Payment rows grouped by status for orders placed in range.

    Counts payment records (multi-attempt orders contribute multiple rows),
    attributed to the order's placed date. Amounts are what the rows state,
    not proof of settlement — see collected revenue in revenue_totals.
    """
    from app.models.payment import Payment

    rows = session.exec(
        select(
            Payment.status,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
        )
        .join(Order, Payment.order_id == Order.id)
        .where(*date_filters(Order.placed_at, from_date, to_date))
        .group_by(Payment.status)
        .order_by(Payment.status)
    ).all()
    return [
        {
            "status": getattr(row[0], "value", str(row[0])),
            "count": row[1] or 0,
            "amount": float(row[2] or 0),
        }
        for row in rows
    ]


def refund_ledger_summary(
    session: Session,
    from_date: date,
    to_date: date,
) -> list[dict]:
    """Refund ledger rows grouped by status (created in range)."""
    from app.models.refund import Refund

    rows = session.exec(
        select(
            Refund.status,
            func.count(Refund.id),
            func.coalesce(func.sum(Refund.amount), 0),
        )
        .where(*date_filters(Refund.created_at, from_date, to_date))
        .group_by(Refund.status)
        .order_by(Refund.status)
    ).all()
    return [
        {
            "status": getattr(row[0], "value", str(row[0])),
            "count": row[1] or 0,
            "amount": float(row[2] or 0),
        }
        for row in rows
    ]


def category_sales(
    session: Session,
    limit: int = 10,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict]:
    """Revenue/units rolled up to categories (same proration as top products)."""
    from app.models.category import Category

    item_totals = select(OrderItem.order_id, func.sum(OrderItem.line_total).label("total")) \
        .group_by(OrderItem.order_id).subquery()
    discounted = item_totals.c.total - Order.discount_total
    discount_ratio = case((discounted > 0, discounted / func.nullif(item_totals.c.total, 0)), else_=0)
    refund_ratio = net_sale_amount() / func.nullif(Order.grand_total, 0)
    merchandise_revenue = OrderItem.line_total * discount_ratio * refund_ratio
    rows = session.exec(
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units"),
            func.coalesce(func.sum(merchandise_revenue), 0).label("revenue"),
            func.count(Order.id.distinct()).label("orders"),
        )
        .select_from(Category)
        .join(Product, Product.category_id == Category.id)
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(OrderItem, OrderItem.variant_id == ProductVariant.id)
        .join(Order, OrderItem.order_id == Order.id)
        .join(item_totals, item_totals.c.order_id == Order.id)
        .where(*date_filters(Order.placed_at, from_date, to_date), settled_sale())
        .group_by(Category.id, Category.name)
        .order_by(func.sum(merchandise_revenue).desc())
        .limit(limit)
    ).all()
    return [
        {
            "category_id": str(row[0]),
            "category_name": row[1],
            "units_sold": int(row[2] or 0),
            "revenue": float(row[3] or 0),
            "order_count": int(row[4] or 0),
        }
        for row in rows
    ]


def slow_products(
    session: Session,
    days: int = 30,
    limit: int = 20,
) -> list[dict]:
    """Products with zero settled units in the last `days` days.

    Includes last settled sale date (None when never sold) so "no recent
    sales" and "never sold" stay distinguishable. DB-side throughout.
    """
    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=max(days - 1, 0))
    settled_units = (
        select(
            Product.id.label("product_id"),
            func.sum(OrderItem.quantity).label("units"),
            func.max(Order.placed_at).label("last_sale"),
        )
        .select_from(Product)
        .join(ProductVariant, ProductVariant.product_id == Product.id)
        .join(OrderItem, OrderItem.variant_id == ProductVariant.id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(
            *date_filters(Order.placed_at, window_start, today), settled_sale(),
        )
        .group_by(Product.id)
        .subquery()
    )
    rows = session.exec(
        select(
            Product.id,
            Product.name,
            Product.slug,
            settled_units.c.last_sale,
        )
        .select_from(Product)
        .outerjoin(settled_units, settled_units.c.product_id == Product.id)
        .where(
            Product.is_active.is_(True),
            func.coalesce(settled_units.c.units, 0) == 0,
        )
        .order_by(Product.name.asc())
        .limit(limit)
    ).all()
    return [
        {
            "product_id": str(row[0]),
            "product_name": row[1],
            "product_slug": row[2],
            "last_sale_date": str(row[3].date()) if row[3] is not None else None,
            "window_days": days,
        }
        for row in rows
    ]


def declining_products(
    session: Session,
    days: int = 7,
    min_prior_units: int = 5,
    drop_ratio: float = 0.5,
    limit: int = 20,
) -> list[dict]:
    """Products whose settled units fell by >= drop_ratio vs the prior window.

    Compares [today-days+1, today] against the equal-length window before
    it; only products with >= min_prior_units prior units qualify, so the
    percentage is meaningful. Transparent arithmetic, DB-side.
    """
    today = datetime.now(timezone.utc).date()
    cur_start = today - timedelta(days=max(days - 1, 0))
    prev_start = cur_start - timedelta(days=days)
    prev_end = cur_start - timedelta(days=1)

    def units_in(start, end):
        return (
            select(
                Product.id.label("product_id"),
                func.sum(OrderItem.quantity).label("units"),
            )
            .select_from(Product)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .join(OrderItem, OrderItem.variant_id == ProductVariant.id)
            .join(Order, OrderItem.order_id == Order.id)
            .where(*date_filters(Order.placed_at, start, end), settled_sale())
            .group_by(Product.id)
            .subquery()
        )

    cur, prev = units_in(cur_start, today), units_in(prev_start, prev_end)
    rows = session.exec(
        select(
            Product.id,
            Product.name,
            func.coalesce(prev.c.units, 0).label("prior_units"),
            func.coalesce(cur.c.units, 0).label("recent_units"),
        )
        .select_from(Product)
        .outerjoin(prev, prev.c.product_id == Product.id)
        .outerjoin(cur, cur.c.product_id == Product.id)
        .where(
            Product.is_active.is_(True),
            func.coalesce(prev.c.units, 0) >= min_prior_units,
            func.coalesce(cur.c.units, 0)
            <= func.coalesce(prev.c.units, 0) * (1.0 - drop_ratio),
        )
        .order_by(
            (func.coalesce(prev.c.units, 0) - func.coalesce(cur.c.units, 0)).desc()
        )
        .limit(limit)
    ).all()
    out = []
    for row in rows:
        prior, recent = int(row[2] or 0), int(row[3] or 0)
        out.append(
            {
                "product_id": str(row[0]),
                "product_name": row[1],
                "prior_units": prior,
                "recent_units": recent,
                "drop_pct": round((prior - recent) / prior * 100, 1) if prior else 0.0,
                "window_days": days,
            }
        )
    return out
