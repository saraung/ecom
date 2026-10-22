"""Checkout must persist the order, reservation, cart and coupon together."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.api.v1 import checkout as api
from app.core import store_settings
from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.coupon import Coupon
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductVariant
from app.models.store_settings import StoreSettings
from app.models.user import User
from app.schemas.checkout import CheckoutRequest


@pytest.fixture
def setup(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    store_settings.invalidate_cache()
    monkeypatch.setattr(api.settings, "SENDGRID_API_KEY", None)
    # Notification delivery is a separate, non-fatal post-commit concern.
    def no_notifications(*args):
        raise RuntimeError("notifications unavailable")
    monkeypatch.setattr(api.notification_repo, "notify_admins_order_placed", no_notifications)
    with Session(engine) as session:
        user = User(email="atomic@example.com", username="atomic", password_hash="x")
        session.add(user)
        session.flush()
        address = Address(user_id=user.id, label="Home", line1="1 Main St",
                          city="Mumbai", state="MH", postal_code="400001", country="India")
        product = Product(name="Atomic", slug="atomic", price=Decimal("1000"))
        session.add(address)
        session.add(product)
        session.flush()
        variant = ProductVariant(product_id=product.id, sku="atomic", stock=3)
        coupon = Coupon(code="ATOMIC", discount_type="percentage", value=Decimal("10"),
                        max_uses=1, max_uses_per_user=1, times_used=0, created_by=user.id,
                        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
                        valid_until=datetime.now(timezone.utc) + timedelta(days=1))
        cart = Cart(user_id=user.id, coupon_code=coupon.code)
        session.add_all([variant, coupon, cart, StoreSettings(id=1)])
        session.flush()
        item = CartItem(cart_id=cart.id, variant_id=variant.id, quantity=2,
                        price_at_add=Decimal("1000"))
        session.add(item)
        session.commit()
        ids = (user.id, address.id, variant.id, cart.id, coupon.id, item.id)
    yield engine, ids
    store_settings.invalidate_cache()
    engine.dispose()


def _place(session, ids):
    return api.checkout(CheckoutRequest(shipping_address_id=ids[1]), session,
                        session.get(User, ids[0]))


def _assert_unchanged(engine, ids):
    with Session(engine) as session:
        assert session.exec(select(Order)).all() == []
        assert session.exec(select(OrderItem)).all() == []
        assert session.get(ProductVariant, ids[2]).stock == 3
        assert session.get(Cart, ids[3]).coupon_code == "ATOMIC"
        assert session.get(CartItem, ids[5]).quantity == 2
        assert session.get(Coupon, ids[4]).times_used == 0


def test_coupon_exhausted_after_pricing_rolls_back_everything(setup, monkeypatch):
    engine, ids = setup
    original = api.resolve_cart_pricing
    def stale_pricing(session, cart, user):
        result = original(session, cart, user)
        # Simulate eligibility changing between the quote and final locked check.
        result.manual.coupon.times_used = 1
        session.flush()
        return result
    monkeypatch.setattr(api, "resolve_cart_pricing", stale_pricing)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            _place(session, ids)
        assert exc.value.status_code == 400
        # A caller continuing to use the session must not commit failed checkout work.
        session.commit()
    _assert_unchanged(engine, ids)


def test_coupon_recording_failure_rolls_back_cart_and_stock(setup, monkeypatch):
    engine, ids = setup
    def fail(*args, **kwargs):
        raise RuntimeError("coupon persistence failed")
    monkeypatch.setattr(api.coupon_repo, "increment_coupon_usage", fail)
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="coupon persistence"):
            _place(session, ids)
        session.commit()
    _assert_unchanged(engine, ids)


def test_success_commits_business_state_once(setup):
    engine, ids = setup
    with Session(engine) as session:
        commits = []
        event.listen(session, "before_commit", lambda s: commits.append(True))
        order = _place(session, ids)
        assert order.coupon_code == "ATOMIC"
        assert len(commits) == 1
    with Session(engine) as session:
        assert len(session.exec(select(Order)).all()) == 1
        assert len(session.exec(select(OrderItem)).all()) == 1
        assert session.get(ProductVariant, ids[2]).stock == 1
        assert session.exec(select(CartItem)).all() == []
        assert session.get(Cart, ids[3]).coupon_code is None
        assert session.get(Coupon, ids[4]).times_used == 1


def test_missing_settings_row_does_not_commit_checkout(setup, monkeypatch):
    engine, ids = setup
    with Session(engine) as session:
        session.delete(session.get(StoreSettings, 1))
        session.commit()
    store_settings.invalidate_cache()
    # Force a cache miss at the session-based policy read.
    original = api.resolve_cart_pricing
    def pricing(session, cart, user):
        result = original(session, cart, user)
        store_settings.invalidate_cache()
        return result
    monkeypatch.setattr(api, "resolve_cart_pricing", pricing)
    with Session(engine) as session:
        commits = []
        event.listen(session, "before_commit", lambda s: commits.append(True))
        _place(session, ids)
        assert len(commits) == 1


def test_retry_consumed_cart_cannot_create_another_order(setup):
    engine, ids = setup
    with Session(engine) as session:
        _place(session, ids)
        with pytest.raises(HTTPException, match="400"):
            _place(session, ids)
    with Session(engine) as session:
        assert len(session.exec(select(Order)).all()) == 1
        assert session.get(ProductVariant, ids[2]).stock == 1
