# tests/test_admin_cancel_stock.py
"""
Functional test: admin cancel path (POST /admin/orders/{id}/cancel).

Verifies:
  1. Admin cancelling an active order RESTORES variant stock (parity with the
     user-facing cancel flow).
  2. Cancelled / refunded orders are TERMINAL — status cannot be flipped back
     (prevents double stock restore via re-cancel).
  3. Shipped / delivered orders cannot be cancelled from the admin panel.
  4. Normal transitions (pending -> shipped) still work and don't touch stock.

Money states (cancelled/refunded) are rejected by PUT
/admin/orders/{id}/status and must go through the unified cancel endpoint.

Run:  PYTHONPATH=. python tests/test_admin_cancel_stock.py
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, OrderItem
from app.models.address import Address
from app.models.product import Product, ProductVariant

from app.api.v1.admin.orders import update_order_status_admin
from app.api.v1.admin.refunds import admin_cancel_order
from app.schemas.order import OrderStatusUpdate
from app.schemas.refund import AdminCancelRequest

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

QTY = 2
STOCK_AFTER_CHECKOUT = 3  # 5 in stock, 2 decremented by the order


def _customer(s) -> User:
    return s.exec(select(User).where(User.role == UserRole.customer)).first()


def _make_order(s, *, status: OrderStatus, sku_prefix: str, product_name: str,
                stock: int, qty: int = 1) -> Order:
    """Create a customer address + product + variant + order + order item."""
    user = _customer(s)
    addr = Address(
        user_id=user.id, label="L", line1="1 Main St", city="Mumbai",
        state="MH", postal_code="400001", country="IN", is_default=False,
    )
    s.add(addr)
    s.commit()
    s.refresh(addr)

    product = Product(
        name=product_name, slug=f"{sku_prefix.lower()}-{uuid4().hex[:6]}",
        price=Decimal("499.00"),
    )
    s.add(product)
    s.commit()
    s.refresh(product)

    variant = ProductVariant(
        product_id=product.id, sku=f"{sku_prefix}-{uuid4().hex[:6]}", stock=stock
    )
    s.add(variant)
    s.commit()
    s.refresh(variant)

    order = Order(
        order_number=f"ORD-{sku_prefix}-{uuid4().hex[:8]}",
        user_id=user.id,
        shipping_address_id=addr.id,
        billing_address_id=addr.id,
        subtotal=Decimal("499.00") * qty,
        tax_total=Decimal("0"),
        shipping_total=Decimal("0"),
        grand_total=Decimal("499.00") * qty,
        payment_method="cod",
        payment_status="pending",
        status=status,
        placed_at=datetime.now(timezone.utc),
    )
    s.add(order)
    s.commit()
    s.refresh(order)

    s.add(OrderItem(
        order_id=order.id, variant_id=variant.id, product_name=product_name,
        variant_sku=variant.sku, variant_attributes={}, quantity=qty,
        unit_price=Decimal("499.00"), line_total=Decimal("499.00") * qty,
    ))
    s.commit()
    return order


def seed() -> tuple:
    """Create the confirmed order used by tests 1-2; returns the order id."""
    with Session(ENGINE) as s:
        order = _make_order(
            s, status=OrderStatus.CONFIRMED, sku_prefix="TEE",
            product_name="Test Tee", stock=STOCK_AFTER_CHECKOUT, qty=QTY,
        )
        return order.id


ADMIN_ID = None
ORDER_ID = None


def _set_status(order_id, new_status):
    """Call the endpoint function directly (bypasses auth Depends)."""
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        try:
            result = update_order_status_admin(
                order_id=order_id,
                status_data=OrderStatusUpdate(status=new_status),
                session=s,
                current_user=admin,
            )
            return result, None
        except HTTPException as e:
            s.rollback()
            return None, e


def _stock(order_id) -> int:
    with Session(ENGINE) as s:
        order = s.get(Order, order_id)
        return s.get(ProductVariant, order.items[0].variant_id).stock


def _admin_cancel(order_id, refund_choice="later"):
    """Call the unified cancel endpoint directly (bypasses auth Depends)."""
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        try:
            result = admin_cancel_order(
                order_id=order_id,
                data=AdminCancelRequest(
                    reason="test cancel", refund_choice=refund_choice
                ),
                session=s,
                request=None,
                current_user=admin,
            )
            return result, None
        except HTTPException as e:
            s.rollback()
            return None, e


def test_1_admin_cancel_restores_stock():
    print("\n=== TEST 1: admin cancel restores stock ===")
    stock_before = _stock(ORDER_ID)
    result, err = _admin_cancel(ORDER_ID)
    assert err is None, err
    assert result["status"] == OrderStatus.CANCELLED.value, result["status"]
    stock_after = _stock(ORDER_ID)
    assert stock_after == stock_before + QTY, (
        f"Expected stock {stock_before + QTY}, got {stock_after}"
    )
    print(f"  ✅ stock {stock_before} -> {stock_after} (+{QTY} restored)")


def test_2_cancelled_order_is_terminal():
    print("\n=== TEST 2: cancelled order cannot be re-activated (no double restore) ===")
    stock_before = _stock(ORDER_ID)
    _, err = _set_status(ORDER_ID, "processing")
    assert err is not None, "Expected HTTPException, got success"
    assert err.status_code == 400, err.status_code
    assert "already cancelled" in err.detail, err.detail
    assert _stock(ORDER_ID) == stock_before, "stock must NOT change"
    print(f"  ✅ 400: {err.detail}")
    print(f"  ✅ stock unchanged at {stock_before}")


def test_3_shipped_order_cannot_be_cancelled():
    print("\n=== TEST 3: shipped order cannot be cancelled from admin ===")
    with Session(ENGINE) as s:
        order = _make_order(
            s, status=OrderStatus.SHIPPED, sku_prefix="MUG",
            product_name="Test Mug", stock=7,
        )
        order_id = order.id
    _, err = _admin_cancel(order_id)
    assert err is not None, "Expected HTTPException, got success"
    assert err.status_code == 400, err.status_code
    assert "cannot be cancelled" in err.detail, err.detail
    assert _stock(order_id) == 7, "stock must NOT change"
    print(f"  ✅ 400: {err.detail}")
    print("  ✅ stock unchanged at 7")


def test_4_refunded_order_is_terminal():
    print("\n=== TEST 4: refunded order status cannot be changed ===")
    with Session(ENGINE) as s:
        order = _make_order(
            s, status=OrderStatus.REFUNDED, sku_prefix="REF",
            product_name="Test Ref", stock=9,
        )
        order_id = order.id
    _, err = _set_status(order_id, "delivered")
    assert err is not None, "Expected HTTPException, got success"
    assert err.status_code == 400, err.status_code
    assert "already refunded" in err.detail, err.detail
    print(f"  ✅ 400: {err.detail}")


def test_5_normal_transition_untouched():
    print("\n=== TEST 5: forward-only workflow (pending -> confirmed ok, jumps rejected) ===")
    with Session(ENGINE) as s:
        order = _make_order(
            s, status=OrderStatus.PENDING, sku_prefix="CAP",
            product_name="Test Cap", stock=4,
        )
        order_id = order.id
    # Legal single step works and doesn't touch stock.
    _, err = _set_status(order_id, "confirmed")
    assert err is None, err
    with Session(ENGINE) as s:
        assert s.get(Order, order_id).status == OrderStatus.CONFIRMED
    assert _stock(order_id) == 4, "stock must NOT change on confirm"
    print("  ✅ status pending -> confirmed, stock unchanged at 4")
    # Skipping stages is rejected (no more silent misclicks).
    _, err = _set_status(order_id, "shipped")
    assert err is not None, "Expected HTTPException, got success"
    assert err.status_code == 400, err.status_code
    assert "Allowed next" in err.detail, err.detail
    print(f"  ✅ 400: {err.detail}")


def _ensure_setup():
    """Seed the in-memory DB once (works for both `python file.py` and pytest)."""
    global ADMIN_ID, ORDER_ID
    if ORDER_ID is None:
        SQLModel.metadata.create_all(ENGINE)
        ADMIN_ID = _admin_id()
        ORDER_ID = seed()
        print(f"Seeded DB (admin={ADMIN_ID}, order={ORDER_ID})")


def _admin_id():
    with Session(ENGINE) as s:
        s.add(User(username="admin", email="admin@test.com", full_name="Admin",
                   hashed_password="x", role=UserRole.admin, is_active=True))
        s.add(User(username="tester", email="tester@test.com", full_name="Test User",
                   hashed_password="x", role=UserRole.customer, is_active=True))
        s.commit()
        return s.exec(select(User).where(User.role == UserRole.admin)).first().id


def run_all():
    test_1_admin_cancel_restores_stock()
    test_2_cancelled_order_is_terminal()
    test_3_shipped_order_cannot_be_cancelled()
    test_4_refunded_order_is_terminal()
    test_5_normal_transition_untouched()
    print("\n🎉 ALL ADMIN CANCEL STOCK TESTS PASSED")


_ensure_setup()

if __name__ == "__main__":
    run_all()

