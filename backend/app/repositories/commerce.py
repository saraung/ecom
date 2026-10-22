"""Shared order-based reporting policy (not a gateway settlement ledger)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func

from app.models.order import Order, OrderStatus


def settled_sale():
    # Staff purchases are real commerce too. An unpaid COD promise is not sales.
    return and_(Order.payment_status == "paid", Order.status.in_([
        OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED,
        OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED,
    ]))


def net_sale_amount():
    remainder = Order.grand_total - func.coalesce(Order.refund_amount, 0)
    return case((remainder > 0, remainder), else_=0)


def date_filters(column, from_date=None, to_date=None):
    filters = []
    if from_date:
        filters.append(column >= datetime.combine(from_date, datetime.min.time(), tzinfo=timezone.utc))
    if to_date:
        filters.append(column < datetime.combine(to_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    return filters
