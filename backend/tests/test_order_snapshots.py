from decimal import Decimal
import importlib.util
from pathlib import Path
from uuid import uuid4
from unittest.mock import Mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from sqlmodel import SQLModel, Session, create_engine

import app.models  # noqa: F401
from app.api.v1.checkout import checkout
from app.api.v1.admin.orders import get_order_detail
from app.models.address import Address
from app.models.cart import Cart, CartItem
from app.models.order import Order
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.repositories.order import get_order_by_id
from app.schemas.checkout import CheckoutRequest
from app.schemas.order import OrderRead
from app.services.email_service import email_service
from app.services.shiprocket_service import RealShiprocketService


@pytest.fixture
def placed(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr("app.core.config.settings.SENDGRID_API_KEY", None)
    with Session(engine) as s:
        user = User(email="original@example.com", username="original", full_name="Original Name",
                    phone="1234567890", password_hash="x")
        s.add(user)
        s.flush()
        address = Address(user_id=user.id, label="Home", line1="Original Street", city="Mumbai",
                          state="MH", postal_code="400001", country="India")
        billing = Address(user_id=user.id, label="Billing", line1="Original Billing", city="Mumbai",
                          state="MH", postal_code="400002", country="India")
        product = Product(name="Snapshot", slug="snapshot", price=Decimal("100"))
        s.add_all([address, billing, product])
        s.flush()
        variant = ProductVariant(product_id=product.id, sku="snapshot", stock=5)
        cart = Cart(user_id=user.id)
        s.add_all([variant, cart])
        s.flush()
        s.add(CartItem(cart_id=cart.id, variant_id=variant.id, quantity=1, price_at_add=Decimal("100")))
        s.commit()
        order = checkout(CheckoutRequest(shipping_address_id=address.id, billing_address_id=billing.id), s, user)
        ids = order.id, user.id, address.id, billing.id
        user.full_name, user.email, user.phone = "Changed", "changed@example.com", "9999999999"
        address.line1, address.postal_code = "Changed Street", "999999"
        billing.line1 = "Changed Billing"
        s.add_all([user, address, billing])
        s.commit()
    yield engine, ids
    engine.dispose()


def test_customer_and_admin_order_responses_preserve_purchase_data(placed):
    engine, ids = placed
    with Session(engine) as s:
        order = get_order_by_id(s, ids[0])
        customer = OrderRead.model_validate(order)
        admin = get_order_detail(order.id, s, s.get(User, ids[1]))
        assert customer.user.full_name == admin["user"]["full_name"] == "Original Name"
        assert customer.user.email == admin["user"]["email"] == "original@example.com"
        assert customer.shipping_address.line1 == admin["shipping_address"]["line1"] == "Original Street"
        assert customer.billing_address.line1 == admin["billing_address"]["line1"] == "Original Billing"
        assert customer.user.phone == "1234567890"


def test_shipping_payload_uses_original_recipient_and_address(placed, monkeypatch):
    engine, ids = placed
    response = Mock(status_code=200)
    response.json.return_value = {"order_id": "sr", "shipment_id": "shipment"}
    post = Mock(return_value=response)
    monkeypatch.setattr("app.services.shiprocket_service.httpx.post", post)
    service = RealShiprocketService()
    monkeypatch.setattr(service, "_headers", lambda: {})
    with Session(engine) as s:
        service.create_order(get_order_by_id(s, ids[0]))
    payload = post.call_args.kwargs["json"]
    assert payload["shipping_address"] == "Original Street"
    assert payload["billing_address"] == "Original Billing"
    assert payload["shipping_phone"] == "1234567890"
    assert payload["shipping_email"] == "original@example.com"


def test_transactional_email_uses_purchase_recipient(placed, monkeypatch):
    engine, ids = placed
    send = Mock(return_value=True)
    monkeypatch.setattr(email_service, "_send_email", send)
    with Session(engine) as s:
        order = get_order_by_id(s, ids[0])
        email_service.send_order_shipped(order, order.user)
    assert send.call_args.args[0] == "original@example.com"
    assert "Original Name" in send.call_args.args[2]


def test_snapshot_migration_backfills_existing_orders(placed):
    engine, ids = placed
    path = Path(__file__).resolve().parents[1] / "alembic/versions/n9b0c1d2e3f4_order_purchase_snapshots.py"
    spec = importlib.util.spec_from_file_location("snapshot_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        # Reproduce the pre-migration schema; verify the real upgrade/backfill.
        for column in ("customer_snapshot", "shipping_snapshot", "billing_snapshot"):
            connection.exec_driver_sql(f"ALTER TABLE orders DROP COLUMN {column}")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    with Session(engine) as s:
        order = s.get(Order, ids[0])
        assert order.customer_snapshot["email"] == "changed@example.com"
        assert order.shipping_snapshot["line1"] == "Changed Street"
        user = s.get(User, ids[1])
        user.email = "another@example.com"
        s.add(user)
        s.commit()
        assert OrderRead.model_validate(get_order_by_id(s, ids[0])).user.email == "changed@example.com"
