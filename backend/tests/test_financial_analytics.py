from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlmodel import SQLModel, Session, create_engine

import app.models  # noqa: F401
from app.api.v1 import analytics as api
from app.models.address import Address
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.repositories import analytics, order as order_repo


@pytest.fixture
def commerce():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    day = datetime.now(timezone.utc).date()
    with Session(engine) as s:
        user = User(email="finance@example.com", username="finance")
        product = Product(name="Finance", slug="finance", price=Decimal("100"))
        s.add_all([user, product])
        s.flush()
        address = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        variant = ProductVariant(product_id=product.id, sku="finance", stock=99)
        s.add_all([address, variant])
        s.flush()
        def add(status=OrderStatus.DELIVERED, payment="paid", amount=100, discount=0, refund=0, staff=False, when=None):
            order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=address.id,
                          billing_address_id=address.id, status=status, payment_status=payment,
                          payment_method="cod" if payment == "cod_pending" else "online",
                          subtotal=Decimal(100 - discount), grand_total=Decimal(amount),
                          discount_total=Decimal(discount), tax_total=Decimal(10 if discount else 0),
                          refund_amount=Decimal(refund), placed_by_staff=staff,
                          placed_at=when or datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc))
            s.add(order)
            s.flush()
            s.add(OrderItem(order_id=order.id, variant_id=variant.id, product_name="Finance", variant_sku="finance",
                            quantity=1, unit_price=Decimal("100"), line_total=Decimal("100")))
            return order
        for state in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED,
                      OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED):
            add(state)
        add(staff=True)
        add(amount=90, discount=20)
        add(refund=20)
        for state, payment in (
            (OrderStatus.PENDING, "pending"), (OrderStatus.PENDING, "paid"),
            (OrderStatus.CONFIRMED, "pending"), (OrderStatus.CONFIRMED, "cod_pending"),
            (OrderStatus.DELIVERED, "cod_pending"), (OrderStatus.CANCELLED, "paid"),
            (OrderStatus.RTO, "paid"), (OrderStatus.REFUNDED, "refund_completed"),
        ):
            add(state, payment, amount=9999)
        s.commit()
        yield s, day, user, add
    engine.dispose()


def test_sales_revenue_dashboard_trend_share_settled_policy(commerce):
    s, day, _, _ = commerce
    sales = analytics.get_sales_report(s, day, day)
    assert sales["summary"] == {"total_sales": 770.0, "order_count": 8, "average_order_value": 96.25}
    revenue = analytics.get_revenue_report(s, day, day)["period_data"][0]
    assert revenue["revenue"] == 790.0
    assert revenue["discounts"] == 20.0
    assert revenue["refunds"] == 20.0
    assert revenue["net_revenue"] == 770.0
    dashboard = analytics.get_dashboard_stats(s)
    assert dashboard["today"]["revenue"] == dashboard["total"]["revenue"] == 770.0
    assert dashboard["total"]["orders"] == 16
    assert analytics.get_sales_trend(s, 1)[0] == {"date": day.isoformat(), "sales": 770.0, "orders": 8}


def test_status_counts_include_all_orders_but_only_settled_money(commerce):
    s, day, _, _ = commerce
    report = analytics.get_order_statistics(s, day, day)
    assert report["total_orders"] == sum(row["count"] for row in report["by_status"]) == 16
    assert sum(row["revenue"] for row in report["by_status"]) == 770.0
    assert all(row["revenue"] == 0 for row in report["by_status"] if row["status"] in ('pending', 'cancelled', 'refunded', 'rto'))


def test_top_products_allocate_discount_refund_and_real_counts(commerce):
    s, day, _, _ = commerce
    product = analytics.get_top_products(s, from_date=day, to_date=day)[0]
    assert product["total_quantity_sold"] == 8
    assert product["total_revenue"] == 760.0
    assert product["average_price"] == 95.0
    assert product["order_count"] == 8 and product["variant_count"] == 1


@pytest.mark.parametrize("group_by", ["day", "week", "month"])
def test_full_end_day_and_next_midnight_bounds(commerce, group_by):
    s, day, _, add = commerce
    add(when=datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    add(when=datetime.combine(day - timedelta(days=1), datetime.max.time(), tzinfo=timezone.utc))
    s.commit()
    report = analytics.get_sales_report(s, day, day, group_by)
    assert report["summary"]["total_sales"] == 770.0
    assert len(report["period_data"]) == 1
    assert analytics.get_revenue_report(s, day, day, group_by)["period_data"][0]["net_revenue"] == 770.0


def test_customer_and_per_user_purchase_metrics_ignore_unsettled_orders(commerce):
    s, day, user, _ = commerce
    customer = analytics.get_customer_summary(s, day, day)
    assert customer["active_customers"] == customer["repeat_customers"] == 1
    stats = order_repo.get_user_order_statistics(s, user.id)
    assert stats["total_orders"] == 16
    assert stats["total_spent"] == 770.0
    assert stats["average_order_value"] == 96.25
    assert stats["total_items_purchased"] == 8


def test_optional_report_ranges_reject_reversed_dates(commerce):
    from fastapi import HTTPException
    s, day, user, _ = commerce
    with pytest.raises(HTTPException) as exc:
        api.get_customer_summary(s, user, day + timedelta(days=1), day)
    assert exc.value.status_code == 400
