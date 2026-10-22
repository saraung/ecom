"""
Functional test for the dashboard daily sales trend.

Verifies `get_sales_trend`:
  1. Returns exactly `days` consecutive daily entries (zero-filled).
  2. Sums ONLY non-cancelled/refunded order revenue for each day.
  3. Days without orders report 0.
  4. Is isolated per date (no cross-day leakage).

Run:  PYTHONPATH=. python tests/test_dashboard_sales_trend.py
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus
from app.models.address import Address

from app.repositories.analytics import get_sales_trend

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})


def _seed():
    SQLModel.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        user = User(
            username="customer", email="customer@test.com", full_name="Customer",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)

        addr = Address(
            user_id=user.id, label="Home", line1="1 Main St", city="Mumbai",
            state="MH", postal_code="400001", country="IN", is_default=True,
        )
        s.add(addr)
        s.commit()
        s.refresh(addr)

        today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)

        def _order(number, status, grand_total, placed_at, staff=False):
            s.add(Order(
                order_number=number,
                user_id=user.id,
                shipping_address_id=addr.id,
                billing_address_id=addr.id,
                subtotal=grand_total,
                discount_total=Decimal("0"),
                tax_total=Decimal("0"),
                shipping_total=Decimal("0"),
                grand_total=grand_total,
                payment_method="cod",
                payment_status="paid",
                status=status,
                placed_at=placed_at,
                placed_by_staff=staff,
                refund_amount=Decimal("0"),
            ))

        # Today: one DELIVERED (counts) + one CANCELLED (must NOT count)
        _order("ORD-100", OrderStatus.DELIVERED, Decimal("500.00"), today)
        _order("ORD-101", OrderStatus.CANCELLED, Decimal("9999.00"), today)
        # Today: staff-placed DELIVERED order — real money, must count too
        _order("ORD-103", OrderStatus.DELIVERED, Decimal("2948.82"), today, staff=True)
        # 3 days ago: one CONFIRMED (counts)
        _order("ORD-102", OrderStatus.CONFIRMED, Decimal("250.00"), today - timedelta(days=3))
        s.commit()


def setup_module():
    _seed()


def test_1_returns_seven_zero_filled_days():
    with Session(ENGINE) as s:
        trend = get_sales_trend(s, days=7)

    assert len(trend) == 7, len(trend)
    # Consecutive dates ending today
    today = date.today()
    for i, entry in enumerate(trend):
        assert entry["date"] == (today - timedelta(days=6 - i)).isoformat(), entry
    # Every day must have sales + orders keys
    for entry in trend:
        assert set(entry.keys()) == {"date", "sales", "orders"}, entry
    print("  ✅ returns 7 consecutive zero-filled days")


def test_2_counts_only_valid_order_statuses():
    with Session(ENGINE) as s:
        trend = get_sales_trend(s, days=7)

    assert trend[-1]["sales"] == 500.0 + 2948.82, trend[-1]  # DELIVERED today (incl. staff order), CANCELLED excluded
    assert trend[-1]["orders"] == 2, trend[-1]
    assert trend[-4]["sales"] == 250.0, trend[-4]  # CONFIRMED 3 days ago
    assert trend[-4]["orders"] == 1, trend[-4]
    # A day with no orders
    assert trend[0]["sales"] == 0, trend[0]
    assert trend[0]["orders"] == 0, trend[0]
    print("  ✅ revenue only from non-cancelled orders; empty days are 0")


if __name__ == "__main__":
    _seed()
    trend = test_1_returns_seven_zero_filled_days()
    test_2_counts_only_valid_order_statuses()
    print("\nAll dashboard-sales-trend tests passed ✅")
