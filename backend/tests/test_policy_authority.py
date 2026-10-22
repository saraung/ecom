from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.core import store_settings as ss
from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.order import Order, OrderStatus
from app.models.product import Product, ProductVariant
from app.models.store_settings import StoreSettings
from app.models.user import User
from app.schemas.checkout import CheckoutRequest
from app.services.pricing import resolve_cart_pricing
from app.services.refund_service import calculate_refund


@pytest.fixture
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'policy.db'}")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.db.database.engine", engine)
    ss.invalidate_cache()
    with Session(engine) as s:
        s.add(StoreSettings(id=1, tax_rate=0.2, shipping_cost=70, free_shipping_threshold=10000,
                            cod_fee=25, cod_min_order_value=0, cod_max_order_value=20000,
                            restocking_fee_confirmed=9))
        user = User(email="policy@example.com", username="policy")
        product = Product(name="Policy", slug="policy", price=Decimal("1000"))
        s.add_all([user, product])
        s.flush()
        addr = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        variant = ProductVariant(product_id=product.id, sku="policy", stock=2)
        cart = Cart(user_id=user.id)
        s.add_all([addr, variant, cart])
        s.flush()
        s.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=1, price_at_add=Decimal("1000")))
        s.commit()
        yield s, user, addr, cart
    ss.invalidate_cache()
    engine.dispose()


def test_session_read_ignores_stale_process_and_identity_map(db):
    s, *_ = db
    stale = s.get(StoreSettings, 1)
    ss._store(ss.StoreSettingsSnapshot(tax_rate=0.99))
    with Session(s.get_bind()) as other:
        row = other.get(StoreSettings, 1)
        row.tax_rate = 0.3
        other.add(row)
        other.commit()
    snapshot = ss.get_store_settings(s, seed=False)
    assert snapshot.tax_rate == 0.3
    assert stale.tax_rate == 0.3


def test_display_cache_expiry_reload_reads_database_not_environment(db):
    s, *_ = db
    assert ss.get_store_settings().tax_rate == 0.2
    with Session(s.get_bind()) as other:
        row = other.get(StoreSettings, 1)
        row.tax_rate = 0.4
        other.add(row)
        other.commit()
    ss._CACHE["expires_at"] = 0
    assert ss.get_store_settings().tax_rate == 0.4


def test_pricing_snapshot_controls_shipping_and_tax_despite_cache(db):
    s, user, _, cart = db
    ss._store(ss.StoreSettingsSnapshot(tax_rate=0.99, shipping_cost=999))
    result = resolve_cart_pricing(s, cart, user)
    assert result.tax_total == Decimal("200")
    assert result.shipping_total == Decimal("70")
    assert result.total == Decimal("1270")


def test_checkout_uses_the_same_snapshot_for_cod_after_policy_edit(db, monkeypatch):
    from app.api.v1 import checkout as api
    s, user, addr, _ = db
    original = api.resolve_cart_pricing
    def pricing(*args):
        result = original(*args)
        with Session(s.get_bind()) as other:
            row = other.get(StoreSettings, 1)
            row.tax_rate, row.cod_fee = 0.9, 999
            other.add(row)
            other.commit()
        return result
    monkeypatch.setattr(api, "resolve_cart_pricing", pricing)
    order = api.checkout(CheckoutRequest(shipping_address_id=addr.id, payment_method="cod"), s, user)
    assert order.tax_total == Decimal("200")
    assert order.cod_fee == Decimal("25")
    assert order.grand_total == Decimal("1295")


def test_refund_calculation_uses_session_policy_instead_of_process_cache(db):
    s, *_ = db
    ss._store(ss.StoreSettingsSnapshot(restocking_fee_confirmed=80))
    order = SimpleNamespace(grand_total=Decimal("1000"), refund_amount=Decimal("0"))
    result = calculate_refund(order, OrderStatus.CONFIRMED, session=s)
    assert result["fee_percentage"] == 9
    assert result["refund_amount"] == Decimal("910")


def test_policy_db_failure_aborts_checkout_without_fallback_or_writes(db, monkeypatch):
    from app.api.v1.checkout import checkout
    s, user, addr, _ = db
    original = s.get
    def unavailable(model, *args, **kwargs):
        if model is StoreSettings:
            raise RuntimeError("policy database unavailable")
        return original(model, *args, **kwargs)
    monkeypatch.setattr(s, "get", unavailable)
    with pytest.raises(HTTPException) as exc:
        checkout(CheckoutRequest(shipping_address_id=addr.id), s, user)
    assert exc.value.status_code == 503
    assert s.exec(select(Order)).all() == []
    assert s.exec(select(CartItem)).one().quantity == 1
    assert s.exec(select(ProductVariant)).one().stock == 2


def test_staged_settings_never_publish_to_display_cache(db):
    s, *_ = db
    original = ss.get_store_settings()
    ss.update_store_settings(s, {"tax_rate": 0.6}, commit=False)
    assert ss._CACHE["snapshot"] == original
    s.rollback()
    assert ss.get_store_settings(s, seed=False).tax_rate == 0.2
