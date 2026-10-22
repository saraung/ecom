"""
Functional test for per-user admin statistics.

Verifies:
  1. `get_user_order_statistics` (repo) returns total orders, total spent,
     gross total, refunded total, average order value, items purchased,
     first/last order timestamps, per-status breakdown and most-purchased
     product for ONE user (isolated from other users).
  2. The endpoint `get_user_order_stats` (GET /admin/users/{id}/stats)
     returns the user_id and 404s for an unknown user.

Run:  PYTHONPATH=. python tests/test_user_order_stats.py
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4, UUID

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, OrderItem
from app.models.address import Address
from app.models.product import Product, ProductVariant

from app.repositories.order import get_user_order_statistics
from app.api.v1.admin.users import get_user_order_stats

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

USER_ID = None
ADMIN_ID = None


def _seed():
    global USER_ID, ADMIN_ID
    SQLModel.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        admin = User(
            username="admin", email="admin@test.com", full_name="Admin",
            hashed_password="x", role=UserRole.admin, is_active=True,
        )
        s.add(admin)
        s.commit()
        s.refresh(admin)
        ADMIN_ID = admin.id

        user = User(
            username="customer", email="customer@test.com", full_name="Customer",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        USER_ID = user.id

        addr = Address(
            user_id=user.id, label="Home", line1="1 Main St", city="Mumbai",
            state="MH", postal_code="400001", country="IN", is_default=True,
        )
        s.add(addr)
        s.commit()
        s.refresh(addr)

        def _variant(name, price):
            product = Product(name=name, slug=f"{name.lower()}-{uuid4().hex[:6]}", price=price)
            s.add(product)
            s.commit()
            s.refresh(product)
            variant = ProductVariant(
                product_id=product.id, sku=f"{name.upper()}-{uuid4().hex[:6]}", stock=10,
            )
            s.add(variant)
            s.commit()
            s.refresh(variant)
            return variant

        def _order(number, status, grand_total, qty, name, variant, placed_at, owner_id, refund=0):
            order = Order(
                order_number=number,
                user_id=owner_id,
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
                refund_amount=refund,
            )
            s.add(order)
            s.commit()
            s.refresh(order)
            s.add(
                OrderItem(
                    order_id=order.id,
                    variant_id=variant.id,
                    product_name=name,
                    variant_sku=variant.sku,
                    variant_attributes={},
                    quantity=qty,
                    unit_price=grand_total,
                    line_total=grand_total * qty,
                )
            )
            s.commit()
            return order

        now = datetime.now(timezone.utc)
        v_widget = _variant("Widget", Decimal("250.00"))
        v_gadget = _variant("Gadget", Decimal("300.00"))

        # DELIVERED  -> counts toward "Total Spent"
        _order("ORD-1001", OrderStatus.DELIVERED, Decimal("500.00"), 2, "Widget", v_widget, now - timedelta(days=30), user.id)
        # CANCELLED  -> excluded from "Total Spent"
        _order("ORD-1002", OrderStatus.CANCELLED, Decimal("300.00"), 1, "Gadget", v_gadget, now - timedelta(days=20), user.id)
        # REFUNDED   -> excluded from "Total Spent", refund_amount tracked
        _order("ORD-1003", OrderStatus.REFUNDED, Decimal("250.00"), 1, "Widget", v_widget, now - timedelta(days=10), user.id, refund=Decimal("250.00"))

        # OTHER user's order — must NOT leak into our stats
        other = User(
            username="other", email="other@test.com", full_name="Other",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(other)
        s.commit()
        s.refresh(other)
        other_addr = Address(
            user_id=other.id, label="O", line1="9 Other St", city="Mumbai",
            state="MH", postal_code="400001", country="IN", is_default=True,
        )
        s.add(other_addr)
        s.commit()
        s.refresh(other_addr)
        o_variant = _variant("OtherProduct", Decimal("999.00"))
        _order("ORD-2001", OrderStatus.DELIVERED, Decimal("999.00"), 5, "OtherProduct", o_variant, now - timedelta(days=1), other.id)


def test_1_repo_returns_correct_user_stats():
    with Session(ENGINE) as s:
        stats = get_user_order_statistics(s, USER_ID)

    assert stats["total_orders"] == 3, stats["total_orders"]
    assert stats["total_spent"] == 500.0, stats["total_spent"]  # only DELIVERED
    assert stats["gross_total"] == 1050.0, stats["gross_total"]  # all 3 orders
    assert stats["refunded_total"] == 250.0, stats["refunded_total"]
    assert stats["average_order_value"] == 500.0, stats["average_order_value"]
    assert stats["total_items_purchased"] == 2, stats["total_items_purchased"]
    assert stats["status_breakdown"]["delivered"] == 1, stats["status_breakdown"]
    assert stats["status_breakdown"]["cancelled"] == 1, stats["status_breakdown"]
    assert stats["status_breakdown"]["refunded"] == 1, stats["status_breakdown"]
    assert stats["status_breakdown"]["pending"] == 0
    assert stats["most_ordered_product"] == "Widget", stats["most_ordered_product"]
    assert stats["last_order"] is not None
    assert stats["first_order"] is not None
    print("  ✅ repo stats match expected values")


def test_2_repo_isolates_users():
    with Session(ENGINE) as s:
        stats = get_user_order_statistics(s, USER_ID)
    assert stats["total_orders"] == 3, "other user's order leaked into stats"
    assert stats["gross_total"] == 1050.0, "other user's revenue leaked into stats"
    print("  ✅ per-user isolation works")


def test_3_endpoint_returns_user_id():
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        result = get_user_order_stats(session=s, user_id=USER_ID, current_user=admin)
    assert str(result["user_id"]) == str(USER_ID), result["user_id"]
    assert result["total_orders"] == 3
    print("  ✅ endpoint returns stats with user_id")


def test_4_endpoint_404_for_unknown_user():
    from app.api.v1.admin.users import get_user_order_stats
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        try:
            get_user_order_stats(session=s, user_id=uuid4(), current_user=admin)
            assert False, "Expected HTTPException 404"
        except HTTPException as e:
            assert e.status_code == 404, e.status_code
            assert "User not found" in e.detail, e.detail
    print("  ✅ 404 raised for unknown user")


def _ensure_setup():
    global USER_ID, ADMIN_ID
    if USER_ID is None:
        _seed()
        print(f"Seeded DB (admin={ADMIN_ID}, user={USER_ID})")


def setup_module():
    _ensure_setup()


if __name__ == "__main__":
    _ensure_setup()
    test_1_repo_returns_correct_user_stats()
    test_2_repo_isolates_users()
    test_3_endpoint_returns_user_id()
    test_4_endpoint_404_for_unknown_user()
    print("\nAll user-order-stats tests passed ✅")
