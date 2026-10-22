# tests/test_workflow_fixes.py
"""Regression tests for the order workflow audit fixes.

1. RTO restock exactly-once: INITIATED then DELIVERED restores once;
   duplicate DELIVERED scans and DELIVERED orders never double-restore.
2. Coupon usage counts once at checkout: cart apply/remove never touches
   times_used.
3. Checkout with exact stock succeeds through the row-locked path.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from sqlmodel import SQLModel, Session, create_engine, select
from starlette.requests import Request

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.core.config import settings
from app.models.address import Address
from app.models.cart import Cart
from app.models.coupon import Coupon
from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductVariant
from app.models.user import User, UserRole
from app.repositories import cart as cart_repo
from app.repositories import coupon as coupon_repo
from app.services.shipping_status import build_tracking_webhook_payload

settings.SENDGRID_API_KEY = None

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(ENGINE)


def _user(s, email, role=UserRole.customer) -> User:
    user = User(
        username=f"u_{uuid4().hex[:8]}", email=email, full_name=email,
        password_hash="x", role=role, is_active=True, email_verified=True,
    )
    s.add(user)
    s.commit()
    s.refresh(user)
    return user


def _addr(s, user) -> Address:
    addr = Address(
        user_id=user.id, label="H", line1="1 Main St", city="Mumbai",
        state="MH", postal_code="400001", country="IN", is_default=True,
    )
    s.add(addr)
    s.commit()
    s.refresh(addr)
    return addr


def _product(s, stock: int, price: str = "499.00"):
    product = Product(name=f"P-{uuid4().hex[:6]}", slug=f"s-{uuid4().hex[:6]}",
                      price=Decimal(price))
    s.add(product)
    s.commit()
    s.refresh(product)
    variant = ProductVariant(product_id=product.id, sku=f"SKU-{uuid4().hex[:6]}",
                             stock=stock)
    s.add(variant)
    s.commit()
    s.refresh(variant)
    return product, variant


def _order(s, user, addr, variant, qty=1, status=OrderStatus.OUT_FOR_DELIVERY,
           awb=None) -> Order:
    from app.models.order import OrderItem

    order = Order(
        order_number=f"ORD-{uuid4().hex[:8]}", user_id=user.id,
        shipping_address_id=addr.id, billing_address_id=addr.id,
        subtotal=Decimal("499.00") * qty, discount_total=Decimal("0"),
        tax_total=Decimal("0"), shipping_total=Decimal("0"),
        grand_total=Decimal("499.00") * qty,
        payment_method="online", payment_status="paid", status=status,
        awb_code=awb or f"AWB{uuid4().hex[:10]}",
        placed_at=datetime.now(timezone.utc),
    )
    s.add(order)
    s.commit()
    s.refresh(order)
    # Stock was conceptually reserved at checkout — mirror it so the
    # restock assertions measure real movement.
    variant.stock -= qty
    s.add(variant)
    s.add(OrderItem(
        order_id=order.id, variant_id=variant.id, product_name="P",
        variant_sku=variant.sku, variant_attributes={}, quantity=qty,
        unit_price=Decimal("499.00"), line_total=Decimal("499.00") * qty,
    ))
    s.commit()
    s.refresh(order)
    return order


def _stock(variant_id) -> int:
    with Session(ENGINE) as s:
        return s.get(ProductVariant, variant_id).stock


def _fire(awb: str, current_status: str) -> dict:
    from app.api.v1.webhooks import shiprocket_tracking_webhook

    payload = build_tracking_webhook_payload(awb=awb, current_status=current_status)
    body = json.dumps(payload).encode()
    state = {"sent": False}

    async def receive():
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "POST",
             "path": "/api/v1/webhooks/shiprocket", "headers": []}
    # Mirror tests/test_shiprocket_shipping.py: .env carries a webhook token,
    # so the endpoint 401s without the header real Shiprocket always sends.
    if getattr(settings, "SHIPROCKET_WEBHOOK_TOKEN", None):
        scope["headers"] = [(b"x-shiprocket-token",
                             settings.SHIPROCKET_WEBHOOK_TOKEN.encode())]
    with Session(ENGINE) as s:
        return asyncio.run(shiprocket_tracking_webhook(Request(scope, receive), s))


def test_rto_initiated_then_delivered_restores_exactly_once():
    with Session(ENGINE) as s:
        user = _user(s, "rto1@t.com")
        addr = _addr(s, user)
        _, variant = _product(s, stock=3)
        order = _order(s, user, addr, variant, qty=2)
        awb, vid, oid = order.awb_code, variant.id, order.id
    assert _stock(vid) == 1, "setup must reserve stock (3-2)"

    _fire(awb, "RTO IN TRANSIT")
    with Session(ENGINE) as s:
        order = s.get(Order, oid)
        assert order.status == OrderStatus.RTO
        assert order.rto_stock_restored is False
    assert _stock(vid) == 1, "INITIATED must not restock (parcel in transit back)"

    _fire(awb, "RTO DELIVERED")
    with Session(ENGINE) as s:
        order = s.get(Order, oid)
        assert order.rto_stock_restored is True
    assert _stock(vid) == 3, "DELIVERED must restore exactly once"

    # Duplicate retry of the same scan must not double-restore.
    _fire(awb, "RTO DELIVERED")
    assert _stock(vid) == 3, "webhook retry must not double-restore stock"


def test_rto_never_restocks_delivered_order():
    with Session(ENGINE) as s:
        user = _user(s, "rto2@t.com")
        addr = _addr(s, user)
        _, variant = _product(s, stock=4)
        order = _order(s, user, addr, variant, status=OrderStatus.DELIVERED)
        awb, vid = order.awb_code, variant.id
    _fire(awb, "RTO DELIVERED")
    assert _stock(vid) == 3, "delivered orders must never restock via RTO"
    with Session(ENGINE) as s:
        assert s.get(Order, order.id).rto_stock_restored is False


def test_coupon_usage_counted_once_at_checkout_not_cart():
    with Session(ENGINE) as s:
        user = _user(s, "coupon@t.com")
        coupon = Coupon(
            code=f"T{uuid4().hex[:6].upper()}", discount_type="percentage",
            value=Decimal("10"), max_uses=100, max_uses_per_user=5,
            valid_from=datetime.now(timezone.utc),
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True, created_by=user.id,
        )
        s.add(coupon)
        s.commit()
        s.refresh(coupon)
        cart = Cart(user_id=user.id)
        s.add(cart)
        s.commit()
        s.refresh(cart)

        # Apply + remove repeatedly: usage counter must not move (orders do that).
        for _ in range(3):
            cart_repo.apply_coupon_to_cart(s, cart, coupon.code)
            cart_repo.remove_coupon_from_cart(s, cart)
        s.refresh(coupon)
        assert coupon.times_used == 0, (
            f"cart apply/remove must not burn usage, got {coupon.times_used}"
        )


def test_checkout_exact_stock_succeeds():
    """End-to-end COD checkout with qty == stock (exercises the locked path)."""
    from app.api.v1.checkout import checkout
    from app.schemas.checkout import CheckoutRequest

    with Session(ENGINE) as s:
        user = _user(s, "buyer@t.com")
        addr = _addr(s, user)
        _, variant = _product(s, stock=2)
        cart = cart_repo.get_or_create_cart(s, user.id)
        cart_repo.add_item_to_cart(s, cart, variant.id, 2)
        uid, aid, vid = user.id, addr.id, variant.id

    with Session(ENGINE) as s:
        user = s.get(User, uid)
        order = checkout(
            checkout_data=CheckoutRequest(
                shipping_address_id=aid, payment_method="cod",
            ),
            session=s,
            current_user=user,
        )
        assert order.grand_total > 0
    assert _stock(vid) == 0, "exact-stock checkout must drain to zero, not fail"
