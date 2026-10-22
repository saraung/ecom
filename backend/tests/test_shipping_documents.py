from decimal import Decimal
from html import escape
from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

import app.models  # noqa: F401
from app.api.v1.admin.orders import router
from app.core.security import create_access_token
from app.db.database import get_session
from app.models.address import Address
from app.models.order import Order
from app.models.rbac import Permission
from app.models.user import User
from app.repositories import rbac


@pytest.fixture
def documents():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    attack = '<script>alert("x")</script>&'
    shipment = 'shipment<script>'
    with Session(engine) as s:
        admin = User(email="docs@example.com", username="docs")
        customer = User(email="customer@example.com", username="customer")
        s.add_all([admin, customer, Permission(key="shipping.manage", label="Shipping", module="shipping")])
        s.commit()
        role = rbac.create_role(s, "Shipping", "shipping", None, ["shipping.manage"])
        rbac.set_user_roles(s, admin, [role])
        address = Address(user_id=customer.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add(address)
        s.flush()
        s.add(Order(order_number=attack, user_id=customer.id, shipping_address_id=address.id,
                    billing_address_id=address.id, subtotal=Decimal("100"), grand_total=Decimal("100"),
                    customer_snapshot={"full_name": attack, "phone": attack},
                    shipping_snapshot={key: attack for key in ("line1", "city", "state", "postal_code")},
                    shiprocket_shipment_id=shipment, courier_name=attack, awb_code=attack))
        s.commit()
        tokens = {"admin": create_access_token(admin.email, "admin"),
                  "customer": create_access_token(customer.email, "customer"),
                  "storefront": create_access_token(admin.email, "admin", audience="storefront")}
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    def db():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = db
    with TestClient(app) as client:
        yield client, tokens, shipment, attack
    engine.dispose()


@pytest.mark.parametrize("kind", ["label", "manifest"])
def test_documents_require_authorized_admin_before_lookup(documents, kind):
    client, tokens, shipment, _ = documents
    url = f"/api/v1/admin/orders/shipping/simulated-{kind}/{quote(shipment, safe='')}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer invalid"}).status_code == 401
    for token in (tokens["customer"], tokens["storefront"]):
        assert client.get(url, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get(url.replace(quote(shipment, safe=''), "missing")).status_code == 401


@pytest.mark.parametrize("kind", ["label", "manifest"])
def test_authorized_documents_escape_purchase_and_shipping_values(documents, kind):
    client, tokens, shipment, attack = documents
    response = client.get(f"/api/v1/admin/orders/shipping/simulated-{kind}/{quote(shipment, safe='')}",
                          headers={"Authorization": f"Bearer {tokens['admin']}"})
    assert response.status_code == 200
    assert attack not in response.text
    assert escape(attack) in response.text
    assert "<script>" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert 'onclick="window.print()"' in response.text
