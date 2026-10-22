"""
HTTP end-to-end harness for the Shiprocket shipping surface (simulator provider).

Unlike the other files in ``tests/`` (which call endpoint functions directly),
this one boots the real FastAPI app on an isolated SQLite database and drives it
through ``TestClient`` — exercising URL routing, auth (manager role), request
validation and response models exactly like the admin dashboard does.

Deliberately NOT named ``test_*.py`` so the normal pytest run does not pick it
up (it swaps ``DATABASE_URL`` before importing the app).

Run:
    cd FAST/Com
    DATABASE_URL=sqlite:////tmp/ship_e2e.db PYTHONPATH=. python tests/http_shiprocket_e2e.py
"""
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

# Must happen before `app` is imported: config reads DATABASE_URL at import time.
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite:////tmp/ship_e2e.db")
# Quiet SQLAlchemy's echo output (it is tied to ENVIRONMENT == "development")
os.environ.setdefault("ENVIRONMENT", "production")

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel, Session  # noqa: E402

import app.models  # noqa: F401,E402
from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.address import Address  # noqa: E402
from app.models.order import Order, OrderItem, OrderStatus  # noqa: E402
from app.models.product import Product, ProductVariant  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

settings.SHIPPING_PROVIDER = "simulator"
settings.SENDGRID_API_KEY = None

API = "/api/v1"
MANAGER_EMAIL = "manager@shipping-e2e.com"
MANAGER_PASSWORD = "SuperSecret123"

client: TestClient | None = None
order_id: str = ""


# ---------------------------------------------------------
# Setup
# ---------------------------------------------------------

def bootstrap() -> None:
    """Fresh schema + one manager, one customer, one order."""
    global client, order_id

    db_path = os.environ["DATABASE_URL"].replace("sqlite:///", "")
    if os.path.exists(db_path):
        os.remove(db_path)

    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        manager = User(
            email=MANAGER_EMAIL, username="shipmanager", full_name="Ship Manager",
            password_hash=hash_password(MANAGER_PASSWORD), role=UserRole.manager,
            is_active=True, email_verified=True,
        )
        customer = User(
            email="buyer@shipping-e2e.com", username="buyer", full_name="Buyer One",
            password_hash=hash_password("BuyerSecret123"), role=UserRole.customer,
            phone="9876543210", is_active=True, email_verified=True,
        )
        s.add(manager)
        s.add(customer)
        s.commit()
        s.refresh(manager)
        s.refresh(customer)

        addr = Address(
            user_id=customer.id, label="Home", line1="42 Marine Drive", city="Mumbai",
            state="MH", postal_code="400020", country="IN", is_default=True,
        )
        s.add(addr)
        product = Product(name="E2E Tee", slug=f"e2e-tee-{uuid4().hex[:6]}",
                          price=Decimal("799.00"))
        s.add(product)
        s.commit()
        s.refresh(addr)
        s.refresh(product)

        variant = ProductVariant(product_id=product.id, sku=f"E2E-{uuid4().hex[:6]}", stock=10)
        s.add(variant)
        s.commit()
        s.refresh(variant)

        order = Order(
            order_number=f"ORD-E2E-{uuid4().hex[:8]}",
            user_id=customer.id,
            shipping_address_id=addr.id,
            billing_address_id=addr.id,
            subtotal=Decimal("799.00"),
            tax_total=Decimal("0"),
            shipping_total=Decimal("0"),
            grand_total=Decimal("799.00"),
            payment_method="online",
            payment_status="paid",
            status=OrderStatus.CONFIRMED,
            placed_at=datetime.now(timezone.utc),
        )
        s.add(order)
        s.commit()
        s.refresh(order)

        s.add(OrderItem(
            order_id=order.id, variant_id=variant.id, product_name=product.name,
            variant_sku=variant.sku, variant_attributes={}, quantity=1,
            unit_price=Decimal("799.00"), line_total=Decimal("799.00"),
        ))
        s.commit()
        order_id = str(order.id)

    client = TestClient(app)
    print(f"Bootstrapped: order={order_id}, provider={settings.SHIPPING_PROVIDER}")


def auth_headers() -> dict:
    r = client.post(f"{API}/auth/login",
                    json={"email": MANAGER_EMAIL, "password": MANAGER_PASSWORD})
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json().get("access_token"), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------
# Scenarios
# ---------------------------------------------------------

def step_1_auth_guard():
    print("\n=== STEP 1: shipping endpoints require a manager token ===")
    r = client.get(f"{API}/admin/orders/shipping/simulator/shipments")
    assert r.status_code == 401, (r.status_code, r.text)
    print("  ✅ unauthenticated /shipping/simulator/shipments -> 401")

    headers = auth_headers()
    print("  ✅ manager login issued an access token")
    return headers


def step_2_serviceability(headers):
    print("\n=== STEP 2: GET serviceability ===")
    r = client.get(f"{API}/admin/orders/{order_id}/shipping/serviceability", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    body = r.json()
    assert body["delivery_pincode"] == "400020", body
    assert len(body["available_couriers"]) >= 2, body
    print(f"  ✅ {len(body['available_couriers'])} couriers, "
          f"routes {body['pickup_pincode']} -> {body['delivery_pincode']}")
    return body["available_couriers"][0]["courier_company_id"]


def step_3_dispatch_chain(headers, courier_id):
    print("\n=== STEP 3: create -> AWB -> pickup (HTTP) ===")
    r = client.post(f"{API}/admin/orders/{order_id}/shipping/create", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    created = r.json()
    assert created["shiprocket_order_id"] and created["shiprocket_shipment_id"], created
    print(f"  ✅ create -> {created['shiprocket_order_id']} / {created['shiprocket_shipment_id']}")

    r = client.post(f"{API}/admin/orders/{order_id}/shipping/assign-awb",
                    headers=headers, json={"courier_id": courier_id})
    assert r.status_code == 200, (r.status_code, r.text)
    awb = r.json()["awb_code"]
    assert awb, r.text
    print(f"  ✅ assign-awb -> {awb} ({r.json()['courier_name']})")

    r = client.post(f"{API}/admin/orders/{order_id}/shipping/request-pickup", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json()["shipment_status"] == "PICKUP_SCHEDULED", r.text
    print(f"  ✅ request-pickup -> {r.json()['shipment_status']}")
    return awb


def step_4_documents_and_tracking(headers, awb):
    print("\n=== STEP 4: label / manifest / tracking (HTTP) ===")
    r = client.get(f"{API}/admin/orders/{order_id}/shipping/label", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    label_url = r.json()["label_url"]
    assert r.json()["is_simulated"] is True, r.text
    print(f"  ✅ label -> {label_url}")

    # The printed label must be served by the app itself (no external hop)
    r2 = client.get(label_url)
    assert r2.status_code == 200, (r2.status_code, r2.text)
    assert awb in r2.text, "AWB must be printed on the simulator label"
    assert r2.headers["content-type"].startswith("text/html"), r2.headers
    print("  ✅ simulator label HTML served (200, text/html, contains AWB)")

    r = client.get(f"{API}/admin/orders/{order_id}/shipping/manifest", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    manifest_url = r.json()["manifest_url"]
    r2 = client.get(manifest_url)
    assert r2.status_code == 200 and awb in r2.text, (r2.status_code, r2.text[:200])
    print(f"  ✅ manifest -> {manifest_url} (served, contains AWB)")

    r = client.get(f"{API}/admin/orders/{order_id}/shipping/tracking", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    tracking = r.json()
    assert tracking["awb_code"] == awb, tracking
    assert tracking["scans"], tracking
    print(f"  ✅ tracking -> {tracking['current_status']} "
          f"({len(tracking['scans'])} scan(s), url={tracking['tracking_url']})")


def step_5_simulator_panel_and_events(headers):
    print("\n=== STEP 5: simulator listing + triggered milestones (HTTP) ===")
    r = client.get(f"{API}/admin/orders/shipping/simulator/shipments", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    listing = r.json()
    assert listing["provider"] == "simulator", listing["provider"]
    row = next((s for s in listing["shipments"] if s["order_id"] == order_id), None)
    assert row is not None, "dispatched order must be listed"
    print(f"  ✅ listed {listing['count']} shipment(s); our order AWB={row['awb_code']}")

    for event, expected_status in (
        ("in_transit", "shipped"),
        ("out_for_delivery", "out_for_delivery"),
    ):
        r = client.post(f"{API}/admin/orders/{order_id}/shipping/simulator/trigger-event",
                        headers=headers, json={"event": event})
        assert r.status_code == 200, (r.status_code, r.text)
        assert r.json()["order_status"] == expected_status, r.text
        print(f"  ✅ trigger {event} -> order_status={r.json()['order_status']} "
              f"shipment={r.json()['shipment_status']}")


def step_6_webhook(headers, awb):
    print("\n=== STEP 6: /webhooks/shiprocket (provider callback, no auth) ===")
    r = client.post(f"{API}/webhooks/shiprocket",
                    json={"awb": awb, "current_status": "DELIVERED", "location": "Doorstep"})
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json()["shipment_status"] == "DELIVERED", r.text
    print(f"  ✅ delivered webhook -> {r.json()}")

    r = client.get(f"{API}/admin/orders/{order_id}", headers=headers)
    assert r.status_code == 200, (r.status_code, r.text)
    detail = r.json()
    assert detail["status"] == "delivered", detail["status"]
    assert detail["delivered_at"], detail
    print(f"  ✅ admin detail reflects status={detail['status']} "
          f"awb={detail['awb_code']} shipment={detail['shipment_status']}")

    # Unknown AWB -> acknowledged, never a 5xx
    r = client.post(f"{API}/webhooks/shiprocket", json={"awb": "UNKNOWN-AWB-1"})
    assert r.status_code == 200 and r.json()["status"] == "ignored", r.text
    print("  ✅ unknown AWB webhook acknowledged as ignored")


def run_all():
    bootstrap()
    headers = step_1_auth_guard()
    courier_id = step_2_serviceability(headers)
    awb = step_3_dispatch_chain(headers, courier_id)
    step_4_documents_and_tracking(headers, awb)
    step_5_simulator_panel_and_events(headers)
    step_6_webhook(headers, awb)
    print("\n🎉 HTTP E2E SHIPROCKET FLOW PASSED")


if __name__ == "__main__":
    try:
        run_all()
    except AssertionError as exc:
        print(f"\n❌ E2E FAILED: {exc}")
        sys.exit(1)

