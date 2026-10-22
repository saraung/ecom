"""Return contracts at real HTTP/auth/RBAC boundaries, plus transaction/race checks."""
import io
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi.staticfiles import StaticFiles
from PIL import Image
from sqlalchemy import event, select
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.api.v1 import orders, returns, webhooks
from app.api.v1.admin import refunds, returns as admin_returns
from app.core.config import settings
from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES
from app.core.security import create_access_token
from app.db.database import get_session
from app.models.address import Address
from app.models.admin_audit import AdminAuditLog
from app.models.order import Order, OrderItem, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product, ProductVariant
from app.models.product_return import ReturnEvidence, ReturnEvent, ReturnItem, ReturnReason, ReturnRequest, ReturnStatus, utcnow
from app.models.rbac import Permission, Role, RolePermissionLink, UserRoleLink
from app.models.refund import Refund, RefundStatus
from app.models.user import User
from app.schemas.product_return import ReturnCreate, ReturnDecision, ReturnInspection, ReturnRefundInput
from app.services import product_return as service, refund_service
from app.services.payment_service import DummyPaymentService


class Gateway(DummyPaymentService):
    requires_refund_reconciliation = True

    def __init__(self):
        self.refunds, self.calls, self.status, self.lost = [], 0, "processed", False

    def get_charge_refund_state(self, payment_id):
        rows = [row for row in self.refunds if row["payment_id"] == payment_id]
        return {"refunds": rows, "charge_total": 556, "currency": "INR",
                "refunded_total": sum(row["amount"] for row in rows if row["status"] in {"processed", "pending"})}

    def create_refund(self, payment_id, amount=None, notes=None):
        self.calls += 1
        row = {"id": "rfnd_return_" + str(self.calls), "amount": amount, "status": self.status,
               "notes": notes, "payment_id": payment_id}
        self.refunds.append(row)
        return {"status": "unknown" if self.lost else self.status, "refund_id": row["id"], "error": "test failure"}


def seed(engine):
    with Session(engine) as s:
        roles = {}
        for key, label, module, description in PERMISSIONS:
            s.add(Permission(key=key, label=label, module=module, description=description))
        s.flush()
        perms = {row.key: row.id for row in s.execute(select(Permission)).scalars()}
        for slug, info in SYSTEM_ROLES.items():
            role = Role(name=info["name"], slug=slug, is_system=True,
                        max_refund_amount=Decimal("50") if slug == "manager" else info["max_refund_amount"])
            s.add(role)
            s.flush()
            roles[slug] = role.id
            for key in info["permissions"]:
                s.add(RolePermissionLink(role_id=role.id, permission_id=perms[key]))
        ids, headers = {}, {}
        for name, slug in (("buyer", "customer"), ("other", "customer"), ("admin", "admin"),
                           ("manager", "manager"), ("staff", "staff")):
            user = User(email=f"{name}@returns.example", username=name, full_name=f"Return {name}", role=slug)
            s.add(user)
            s.flush()
            s.add(UserRoleLink(user_id=user.id, role_id=roles[slug]))
            ids[name] = user.id
            headers[name] = {"Authorization": "Bearer " + create_access_token(user.email, slug,
                audience="storefront" if slug == "customer" else "admin")}
            headers[name + "_storefront"] = {"Authorization": "Bearer " + create_access_token(user.email, slug, audience="storefront")}
        address = Address(user_id=ids["buyer"], line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add(address)
        s.flush()
        order = Order(order_number="ORD-RETURN-TEST", user_id=ids["buyer"], shipping_address_id=address.id,
                      billing_address_id=address.id, subtotal=Decimal("500"), discount_total=Decimal("50"),
                      tax_total=Decimal("81"), shipping_total=Decimal("25"), grand_total=Decimal("556"),
                      payment_method="online", payment_status="paid", status=OrderStatus.DELIVERED, delivered_at=utcnow())
        s.add(order)
        s.flush()
        ids["order"] = order.id
        for index, qty, price in ((1, 3, 100), (2, 1, 200)):
            product = Product(name=f"Current name {index}", slug=f"return-product-{index}", price=Decimal(price))
            s.add(product)
            s.flush()
            variant = ProductVariant(product_id=product.id, sku=f"SKU-{index}", stock=10)
            s.add(variant)
            s.flush()
            item = OrderItem(order_id=order.id, variant_id=variant.id, product_name=f"Purchased product {index}",
                             variant_sku=variant.sku, variant_attributes={"size": "M"}, quantity=qty,
                             unit_price=Decimal(price), line_total=Decimal(price * qty))
            s.add(item)
            ids[f"item{index}"], ids[f"variant{index}"] = item.id, variant.id
        payment = Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_return",
                          provider_payment_intent="pay_return", amount=Decimal("556"), status=PaymentStatus.SUCCEEDED)
        s.add(payment)
        ids["payment"] = payment.id
        s.commit()
        return ids, headers


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    ids, headers = seed(engine)
    gateway = Gateway()
    monkeypatch.setattr(refund_service, "get_payment_service_for_payment", lambda payment: gateway)
    assets, deleted = {}, []
    def upload(blob, folder, private=False, filename=None):
        public_id = f"{folder}/test-{uuid4().hex}"
        assets[public_id] = blob
        return {"public_id": public_id, "secure_url": f"https://res.cloudinary.test/{public_id}.jpg",
                "type": "authenticated" if private else "upload", "bytes": len(blob)}
    def delete(public_id, private=False):
        deleted.append((public_id, private))
        assets.pop(public_id, None)
    monkeypatch.setattr(service, "upload_image", upload)
    monkeypatch.setattr(returns, "delete_image", delete)
    monkeypatch.setattr(settings, "RETURN_STORAGE_DIR", str(tmp_path / "private"))
    for key, value in {"RETURNS_ENABLED": True, "RETURN_WINDOW_DAYS": None, "RETURN_EXCLUDED_VARIANT_IDS": [],
                       "RETURN_REQUIRED_PHOTO_REASONS": [], "RETURN_FEE_PERCENT": 0, "RETURN_MAX_IMAGES": 6,
                       "RETURN_IMAGE_MAX_BYTES": 5 * 1024 * 1024}.items():
        monkeypatch.setattr(settings, key, value)
    app = FastAPI()
    for router in (returns.router, admin_returns.router, refunds.router, orders.router, webhooks.router):
        app.include_router(router, prefix="/api/v1")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    app.mount("/uploads", StaticFiles(directory=uploads))
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_session] = db
    monkeypatch.setattr(returns, "fetch_private_image", lambda public_id: (assets[public_id], "image/jpeg"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SimpleNamespace(client=client, engine=engine, ids=ids, headers=headers, gateway=gateway,
                              path=tmp_path, assets=assets, deleted=deleted)
    engine.dispose()


def payload(env, qty=1, reason="damaged", **extra):
    return {"idempotency_key": str(uuid4()), "reason": reason, "description": "Parcel arrived damaged",
            "items": [{"order_item_id": str(env.ids["item1"]), "quantity": qty}], **extra}


def submit(env, data=None, images=None, actor="buyer", order=None):
    return env.client.post(f"/api/v1/orders/{order or env.ids['order']}/returns", headers=env.headers[actor],
                           data={"data": json.dumps(data or payload(env))}, files=images or [])


def action(env, return_id, name, data=None, actor="admin"):
    return env.client.post(f"/api/v1/admin/returns/{return_id}/{name}", headers=env.headers[actor], json=data or {})


def create(env, data=None, images=None, actor="buyer"):
    response = submit(env, data, images, actor)
    assert response.status_code == 201, response.text
    return response.json()


def inspected(env, data=None, actor="buyer"):
    row = create(env, data, actor=actor)
    assert action(env, row["id"], "decision", {"decision": "approve"}).status_code == 200
    assert action(env, row["id"], "receive").status_code == 200
    response = action(env, row["id"], "inspection", {"passed": True, "note": "All selected items verified"})
    assert response.status_code == 200, response.text
    return response.json()


def patch_order(env, **values):
    with Session(env.engine) as s:
        order = s.get(Order, env.ids["order"])
        for key, value in values.items():
            setattr(order, key, value)
        s.add(order)
        s.commit()


def photo(blob=None, name="evidence.png", mime="image/png"):
    if blob is None:
        stream = io.BytesIO()
        Image.new("RGB", (12, 12), "red").save(stream, format="PNG")
        blob = stream.getvalue()
    return ("files", (name, blob, mime))


@pytest.mark.parametrize("reason", [reason.value for reason in ReturnReason])
def test_all_reasons_are_accepted_and_historical_item_details_are_used(env, reason):
    row = create(env, payload(env, reason=reason))
    assert row["reason"] == reason and row["status"] == "requested"
    assert row["items"][0]["product_name"] == "Purchased product 1"
    assert row["refund_amount"] == "106.20" and row["return_fee"] == "0.00"
    assert row["history"][0]["action"] == "requested"


@pytest.mark.parametrize("status", [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
                                    OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED, OrderStatus.RTO])
def test_non_delivered_orders_are_rejected_on_backend(env, status):
    patch_order(env, status=status, delivered_at=None)
    assert not env.client.get(f"/api/v1/orders/{env.ids['order']}/return-eligibility", headers=env.headers["buyer"]).json()["eligible"]
    assert submit(env).status_code == 409


def test_unpaid_or_uncollected_cod_cannot_request_return(env):
    patch_order(env, payment_status="pending")
    assert submit(env).status_code == 409
    patch_order(env, payment_method="cod", payment_status="cod_pending")
    assert submit(env).status_code == 409
    patch_order(env, payment_status="paid")
    assert submit(env).status_code == 409  # an online payment row is not COD collection


def test_disabled_window_and_product_policy_are_server_authoritative(env, monkeypatch):
    monkeypatch.setattr(settings, "RETURNS_ENABLED", False)
    assert submit(env).status_code == 409
    monkeypatch.setattr(settings, "RETURNS_ENABLED", True)
    monkeypatch.setattr(settings, "RETURN_WINDOW_DAYS", 7)
    patch_order(env, delivered_at=utcnow() - timedelta(days=8))
    assert submit(env).status_code == 409
    patch_order(env, delivered_at=None)
    assert submit(env).status_code == 409
    patch_order(env, delivered_at=utcnow())
    monkeypatch.setattr(settings, "RETURN_EXCLUDED_VARIANT_IDS", [str(env.ids["variant1"])])
    assert submit(env).status_code == 409
    assert create(env, payload(env, items=[{"order_item_id": str(env.ids["item2"]), "quantity": 1}]))["items"][0]["quantity"] == 1


@pytest.mark.parametrize("change", [
    {"reason": "invalid"}, {"reason": "other", "description": "   "}, {"reason": "other", "description": "short"},
    {"items": []}, {"items": [{"order_item_id": str(uuid4()), "quantity": 0}]},
    {"items": [{"order_item_id": str(uuid4()), "quantity": 1.5}]}, {"status": "approved"},
])
def test_invalid_submission_shape_and_other_explanation(env, change):
    assert submit(env, payload(env, **change)).status_code == 422


def test_wrong_order_item_duplicate_item_and_excess_quantity(env):
    assert submit(env, payload(env, items=[{"order_item_id": str(uuid4()), "quantity": 1}])).status_code == 422
    duplicate = [{"order_item_id": str(env.ids["item1"]), "quantity": 1}] * 2
    assert submit(env, payload(env, items=duplicate)).status_code == 422
    assert submit(env, payload(env, qty=4)).status_code == 409


def test_multi_item_partial_quantity_and_completed_overlap(env):
    first = inspected(env, payload(env, items=[{"order_item_id": str(env.ids["item1"]), "quantity": 2},
                                             {"order_item_id": str(env.ids["item2"]), "quantity": 1}]))
    response = action(env, first["id"], "refund")
    assert response.status_code == 200 and response.json()["status"] == "refunded", response.text
    assert response.json()["refund_amount"] == "424.80"
    assert submit(env, payload(env, qty=2)).status_code == 409
    last = inspected(env)
    assert action(env, last["id"], "refund").json()["status"] == "refunded"
    assert submit(env).status_code == 409
    with Session(env.engine) as s:
        order = s.get(Order, env.ids["order"])
        assert order.refund_amount == Decimal("531") and order.status == OrderStatus.DELIVERED
        assert order.restocking_fee == 0 and not order.stock_released
        assert s.get(ProductVariant, env.ids["variant1"]).stock == 10


def test_same_submission_replays_identically_and_rejects_key_reuse(env):
    data = payload(env)
    row = create(env, data, [photo(), photo()])
    assert create(env, data, [photo(), photo()])["id"] == row["id"]
    assert submit(env, {**data, "description": "Changed description"}, [photo(), photo()]).status_code == 409
    assert submit(env, data, [photo()]).status_code == 409
    with Session(env.engine) as s:
        assert len(s.execute(select(ReturnRequest)).scalars().all()) == 1
        assert len(s.execute(select(ReturnEvidence)).scalars().all()) == 2
    assert len(env.assets) == 2


def test_active_quantities_are_reserved_and_rejection_and_cancel_release_them(env):
    row = create(env, payload(env, qty=3))
    assert submit(env).status_code == 409
    assert action(env, row["id"], "decision", {"decision": "reject", "note": "Not eligible after review"}).status_code == 200
    second = create(env, payload(env, qty=3))
    response = env.client.post(f"/api/v1/returns/{second['id']}/cancel", json={}, headers=env.headers["buyer"])
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert create(env)["status"] == "requested"


def test_ownership_is_enforced_for_all_customer_reads_and_writes(env):
    row = create(env, images=[photo()])
    assert submit(env, actor="other").status_code == 404
    assert env.client.get(f"/api/v1/orders/{env.ids['order']}/return-eligibility", headers=env.headers["other"]).status_code == 404
    assert env.client.get("/api/v1/returns", headers=env.headers["other"]).json()["total"] == 0
    base = f"/api/v1/returns/{row['id']}"
    for path in (base, base + "/evidence/" + row["evidence"][0]["id"]):
        assert env.client.get(path, headers=env.headers["other"]).status_code == 404
        assert env.client.get(path).status_code == 401
    for suffix, body in (("cancel", {}), ("tracking", {"tracking_number": "reverse123", "courier_name": "Courier"})):
        assert env.client.post(base + "/" + suffix, json=body, headers=env.headers["other"]).status_code == 404
    assert env.client.post(base + "/evidence", files=[photo()], headers=env.headers["other"]).status_code == 404


@pytest.mark.parametrize("actor", ["buyer", "admin_storefront", "staff"])
def test_admin_mutations_require_permission_and_admin_audience(env, actor):
    row = create(env)
    for name, body in (("decision", {"decision": "approve"}), ("receive", {}),
                       ("inspection", {"passed": True, "note": "Checked"}), ("refund", {}), ("cancel", {}),
                       ("tracking", {"tracking_number": "reverse123", "courier_name": "Courier"}), ("tracking/sync", {})):
        assert action(env, row["id"], name, body, actor=actor).status_code == 403
    if actor != "staff":
        assert env.client.get("/api/v1/admin/returns", headers=env.headers[actor]).status_code == 403


def test_rejection_note_and_state_transitions_are_enforced(env):
    row = create(env)
    assert action(env, row["id"], "decision", {"decision": "reject"}).status_code == 422
    assert action(env, row["id"], "receive").status_code == 409
    assert action(env, row["id"], "inspection", {"passed": True, "note": "Not received"}).status_code == 409
    assert action(env, row["id"], "refund").status_code == 409
    rejected = action(env, row["id"], "decision", {"decision": "reject", "note": "Please contact support"}).json()
    assert rejected["decision_note"] == "Please contact support" and rejected["rejected_at"]
    assert action(env, row["id"], "decision", {"decision": "approve"}).status_code == 409
    assert action(env, row["id"], "refund").status_code == 409
    assert env.gateway.calls == 0


def test_failed_inspection_cannot_refund_and_pass_requires_explicit_confirmation(env):
    row = create(env)
    action(env, row["id"], "decision", {"decision": "approve"})
    assert action(env, row["id"], "refund").status_code == 409
    action(env, row["id"], "receive")
    assert action(env, row["id"], "refund").status_code == 409
    assert action(env, row["id"], "inspection", {"passed": False, "note": "Missing selected unit"}).json()["status"] == "inspection"
    assert action(env, row["id"], "refund").status_code == 409
    assert action(env, row["id"], "inspection", {"passed": True, "note": "Complete after review"}).status_code == 200
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    assert action(env, row["id"], "receive").status_code == 409


def test_tracking_requires_approval_and_shiprocket_delivery_only_receives(env):
    row = create(env)
    data = {"tracking_number": "REVERSE-123", "courier_name": "Return courier", "provider": "shiprocket"}
    assert action(env, row["id"], "tracking", data).status_code == 409
    action(env, row["id"], "decision", {"decision": "approve"})
    assert env.client.post(f"/api/v1/returns/{row['id']}/tracking", headers=env.headers["buyer"], json=data).status_code == 403
    assert action(env, row["id"], "tracking", data).json()["status"] == "return_shipped"
    assert action(env, row["id"], "tracking", data).status_code == 200  # idempotent attachment
    assert env.client.post(f"/api/v1/returns/{row['id']}/cancel", headers=env.headers["buyer"], json={}).status_code == 409
    with Session(env.engine) as s:
        scan = {"awb": "REVERSE-123", "current_status": "DELIVERED", "date": "2026-10-05 12:00", "location": {"name": "Warehouse"}}
        for _ in range(2):
            assert webhooks.process_tracking_event(s, scan)["return_status"] == "received"
        webhooks.process_tracking_event(s, {**scan, "current_status": "IN TRANSIT", "date": "older"})
        request = s.get(ReturnRequest, UUID(row["id"]))
        assert request.status == ReturnStatus.RECEIVED and request.received_at and request.inspection_passed is None
        assert len(s.execute(select(ReturnEvent).where(ReturnEvent.action == "tracking_scan")).scalars().all()) == 2
        assert s.get(Order, env.ids["order"]).status == OrderStatus.DELIVERED
        assert s.get(ProductVariant, env.ids["variant1"]).stock == 10
    assert action(env, row["id"], "refund").status_code == 409 and env.gateway.calls == 0


def test_customer_manual_tracking_and_awb_collision_are_safe(env):
    row = create(env)
    action(env, row["id"], "decision", {"decision": "approve"})
    patch_order(env, awb_code="OUTBOUND-123")
    data = {"tracking_number": "OUTBOUND-123", "courier_name": "Courier"}
    assert action(env, row["id"], "tracking", data).status_code == 409
    data["tracking_number"] = "MANUAL-123"
    response = env.client.post(f"/api/v1/returns/{row['id']}/tracking", headers=env.headers["buyer"], json=data)
    assert response.status_code == 200 and response.json()["status"] == "return_shipped"
    with Session(env.engine) as s:
        assert service.tracking_event(s, "MANUAL-123", {"current_status": "DELIVERED"}) is None
    assert action(env, row["id"], "tracking/sync").status_code == 409


def test_provider_sync_uses_existing_tracking_interface_without_refunding(env, monkeypatch):
    row = create(env)
    action(env, row["id"], "decision", {"decision": "approve"})
    action(env, row["id"], "tracking", {"tracking_number": "REVERSE-SYNC", "courier_name": "Courier", "provider": "shiprocket"})
    provider = SimpleNamespace(get_tracking=lambda awb: {"tracking_data": {"shipment_track": [
        {"sr-status-label": "DELIVERED", "date": "test scan", "location": {"name": "Warehouse"}}]}})
    monkeypatch.setattr(admin_returns, "get_shipping_service", lambda: provider)
    response = action(env, row["id"], "tracking/sync")
    assert response.status_code == 200 and response.json()["status"] == "received"
    assert response.json()["history"][-1]["details"]["location"] == "Warehouse" and env.gateway.calls == 0


def test_negative_delivery_and_outbound_rto_labels_cannot_receive_a_return(env):
    row = create(env)
    action(env, row["id"], "decision", {"decision": "approve"})
    action(env, row["id"], "tracking", {"tracking_number": "REVERSE-NEGATIVE", "courier_name": "Courier", "provider": "shiprocket"})
    with Session(env.engine) as s:
        for label in ("UNDELIVERED", "NOT DELIVERED", "RTO DELIVERED"):
            result = webhooks.process_tracking_event(s, {"awb": "REVERSE-NEGATIVE", "current_status": label})
            assert result["return_status"] == "return_shipped"
        assert s.get(ReturnRequest, UUID(row["id"])).received_at is None
        assert s.get(ProductVariant, env.ids["variant1"]).stock == 10
    assert env.gateway.calls == 0


def test_malformed_tracking_provider_response_does_not_mutate_return(env, monkeypatch):
    row = create(env)
    action(env, row["id"], "decision", {"decision": "approve"})
    action(env, row["id"], "tracking", {"tracking_number": "REVERSE-BAD", "courier_name": "Courier", "provider": "shiprocket"})
    monkeypatch.setattr(admin_returns, "get_shipping_service", lambda: SimpleNamespace(get_tracking=lambda awb: []))
    assert action(env, row["id"], "tracking/sync").status_code == 502
    assert env.client.get(f"/api/v1/returns/{row['id']}", headers=env.headers["buyer"]).json()["status"] == "return_shipped"


def test_return_refund_uses_existing_authority_and_four_eyes(env):
    row = inspected(env)
    response = action(env, row["id"], "refund", actor="manager")
    assert response.status_code == 200, response.text
    queued = response.json()
    assert queued["status"] == "refund_pending" and queued["refund"]["requires_approval"] and env.gateway.calls == 0
    refund_id = queued["refund"]["id"]
    approve = f"/api/v1/admin/refunds/{refund_id}/approve"
    assert env.client.post(approve, headers=env.headers["manager"]).status_code == 400
    assert env.client.post(approve, headers=env.headers["buyer"]).status_code == 403
    assert env.client.post(approve, headers=env.headers["admin"]).status_code == 200
    result = env.client.get(f"/api/v1/returns/{row['id']}", headers=env.headers["buyer"]).json()
    assert result["status"] == "refunded" and result["refunded_at"] and env.gateway.calls == 1
    assert action(env, row["id"], "refund").json()["status"] == "refunded" and env.gateway.calls == 1


def test_rejected_refund_approval_returns_to_inspection_for_explicit_retry(env):
    row = inspected(env)
    queued = action(env, row["id"], "refund", actor="manager").json()
    assert env.client.post(f"/api/v1/admin/refunds/{queued['refund']['id']}/reject", json={"note": "Recheck authorization"},
                           headers=env.headers["admin"]).status_code == 200
    assert env.client.get(f"/api/v1/returns/{row['id']}", headers=env.headers["buyer"]).json()["status"] == "inspection"
    retry = action(env, row["id"], "refund").json()
    assert retry["status"] == "refunded" and env.gateway.calls == 1
    with Session(env.engine) as s:
        assert len(s.execute(select(Refund)).scalars().all()) == 2


def test_provider_pending_completion_and_failure_are_per_linked_return(env):
    env.gateway.status = "pending"
    first = inspected(env)
    assert action(env, first["id"], "refund").json()["status"] == "refund_pending"
    second = inspected(env)
    assert action(env, second["id"], "refund").json()["status"] == "refund_pending"
    with Session(env.engine) as s:
        webhooks._handle_refund_webhook(s, "refund.processed", {"id": "rfnd_return_1"})
        assert s.get(ReturnRequest, UUID(first["id"])).status == ReturnStatus.REFUNDED
        assert s.get(ReturnRequest, UUID(second["id"])).status == ReturnStatus.REFUND_PENDING
        for _ in range(2):
            webhooks._handle_refund_webhook(s, "refund.failed", {"id": "rfnd_return_2"})
        assert s.get(ReturnRequest, UUID(second["id"])).status == ReturnStatus.INSPECTION
        assert s.get(Order, env.ids["order"]).refund_amount == Decimal("106.20")
    env.gateway.refunds[0]["status"], env.gateway.refunds[1]["status"] = "processed", "failed"
    env.gateway.status = "processed"
    assert action(env, second["id"], "refund").json()["status"] == "refunded"
    assert env.gateway.calls == 3


def test_existing_reconciliation_completes_linked_return(env):
    env.gateway.status = "pending"
    row = inspected(env)
    action(env, row["id"], "refund")
    env.gateway.refunds[0]["status"] = "processed"
    response = env.client.post(f"/api/v1/admin/orders/{env.ids['order']}/reconcile-refund", headers=env.headers["admin"])
    assert response.status_code == 200, response.text
    assert env.client.get(f"/api/v1/returns/{row['id']}", headers=env.headers["buyer"]).json()["status"] == "refunded"


def test_unknown_provider_result_recovers_same_attempt_without_duplicate_money(env):
    row = inspected(env)
    env.gateway.lost = True
    assert action(env, row["id"], "refund").status_code == 503
    with Session(env.engine) as s:
        assert s.execute(select(Refund)).scalars().all() == []
        assert s.get(ReturnRequest, UUID(row["id"])).status == ReturnStatus.INSPECTION
        assert s.get(ReturnRequest, UUID(row["id"])).refund_attempts == 0
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    assert env.gateway.calls == 1


def test_direct_refund_execution_cannot_bypass_inspection_or_authority(env):
    row = create(env)
    with Session(env.engine) as s:
        order = s.get(Order, env.ids["order"])
        for approver in (None, env.ids["staff"], env.ids["admin"]):
            with pytest.raises(HTTPException):
                refund_service.process_refund(s, order, OrderStatus.DELIVERED, amount=Decimal("106.20"),
                    approved_by=approver, idempotency_key="invalid", return_request_id=UUID(row["id"]))
    assert env.gateway.calls == 0


def test_existing_generic_refund_preserves_reserved_return_money(env):
    row = inspected(env, payload(env, qty=3))
    with Session(env.engine) as s:
        result = refund_service.process_refund(s, s.get(Order, env.ids["order"]), OrderStatus.DELIVERED,
                                                idempotency_key="legacy-generic", amount=Decimal("556"))
        assert result["amount"] == Decimal("237.40")
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    assert env.gateway.calls == 2


def test_return_fee_is_captured_separately_from_cancellation_policy(env, monkeypatch):
    monkeypatch.setattr(settings, "RETURN_FEE_PERCENT", 10)
    row = inspected(env)
    assert row["refund_amount"] == "95.58" and row["return_fee"] == "10.62"
    monkeypatch.setattr(settings, "RETURN_FEE_PERCENT", 50)
    assert action(env, row["id"], "refund").json()["refund"]["amount"] == "95.58"
    with Session(env.engine) as s:
        assert s.get(Order, env.ids["order"]).restocking_fee == 0


def test_cod_return_records_attested_repayment_without_calling_online_provider(env):
    patch_order(env, payment_method="cod")
    with Session(env.engine) as s:
        payment = s.get(Payment, env.ids["payment"])
        payment.provider = "cod"
        s.add(payment)
        s.commit()
    row = inspected(env)
    assert action(env, row["id"], "refund").status_code == 422
    response = action(env, row["id"], "refund", {"manual_transfer_reference": "BANK-RETURN-123"})
    assert response.status_code == 200 and response.json()["status"] == "refunded", response.text
    assert response.json()["refund"]["manual_transfer_reference"] == "BANK-RETURN-123"
    assert env.gateway.calls == 0
    assert action(env, row["id"], "refund", {"manual_transfer_reference": "BANK-RETURN-123"}).status_code == 200
    another = inspected(env)
    assert action(env, another["id"], "refund", {"manual_transfer_reference": "BANK-RETURN-123"}).status_code == 409
    assert action(env, another["id"], "refund", {"manual_transfer_reference": "BANK-RETURN-456"}, actor="manager").json()["refund"]["requires_approval"]
    assert env.gateway.calls == 0


def test_online_refund_cannot_be_replaced_with_manual_attestation(env):
    row = inspected(env)
    assert action(env, row["id"], "refund", {"manual_transfer_reference": "MANUAL-123"}).status_code == 422
    assert env.gateway.calls == 0


def test_private_images_are_multiple_sanitized_and_owner_admin_only(env):
    raw = photo()[1][1] + b"<?php malicious_code(); ?>"
    row = create(env, images=[photo(raw), photo()])
    assert len(row["evidence"]) == 2
    image_id = row["evidence"][0]["id"]
    path = f"/api/v1/returns/{row['id']}/evidence/{image_id}"
    response = env.client.get(path, headers=env.headers["buyer"])
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert b"malicious_code" not in response.content and response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert env.client.get(f"/api/v1/admin/returns/{row['id']}/evidence/{image_id}", headers=env.headers["admin"]).status_code == 200
    assert env.client.get(f"/api/v1/admin/returns/{row['id']}/evidence/{image_id}", headers=env.headers["buyer"]).status_code == 403
    with Session(env.engine) as s:
        image = s.get(ReturnEvidence, UUID(image_id))
        assert image.cloudinary_public_id and image.cloudinary_type == "authenticated"
        assert image.cloudinary_public_id.startswith(f"com/returns/{row['id']}/")
        assert env.client.get("/uploads/returns/" + image.storage_key).status_code == 404
    assert env.client.get(path).status_code == 401
    assert env.client.get(path, headers=env.headers["other"]).status_code == 404
    assert all("secure_url" not in evidence and "cloudinary_public_id" not in evidence for evidence in row["evidence"])
    another = create(env)
    assert env.client.get(f"/api/v1/returns/{another['id']}/evidence/{image_id}", headers=env.headers["buyer"]).status_code == 404


@pytest.mark.parametrize("upload", [photo(b"<script>attack</script>"), photo(b"<?php attack ?>", "image.php", "image/png"),
                                   photo(b"<svg onload='attack' />", "image.svg", "image/svg+xml"),
                                   photo(name="image.png", mime="text/html")])
def test_invalid_and_executable_evidence_is_rejected(env, upload):
    assert submit(env, images=[upload]).status_code == 415
    with Session(env.engine) as s:
        assert s.execute(select(ReturnRequest)).scalars().all() == []


def test_image_size_count_required_reason_and_upload_state(env, monkeypatch):
    monkeypatch.setattr(settings, "RETURN_IMAGE_MAX_BYTES", 100)
    assert submit(env, images=[photo(b"x" * 101)]).status_code == 413
    monkeypatch.setattr(settings, "RETURN_IMAGE_MAX_BYTES", 5 * 1024 * 1024)
    assert submit(env, images=[photo()] * 7).status_code == 422
    monkeypatch.setattr(settings, "RETURN_REQUIRED_PHOTO_REASONS", ["damaged"])
    assert submit(env).status_code == 422
    assert create(env, payload(env, reason="changed_mind"))["evidence"] == []
    row = create(env, images=[photo()])
    url = f"/api/v1/returns/{row['id']}/evidence"
    assert env.client.post(url, files=[photo()] * 5, headers=env.headers["buyer"]).status_code == 200
    assert env.client.post(url, files=[photo()], headers=env.headers["buyer"]).status_code == 422
    action(env, row["id"], "decision", {"decision": "approve"})
    assert env.client.post(url, files=[photo()], headers=env.headers["buyer"]).status_code == 409


def test_evidence_and_audit_roll_back_together_on_failed_commit(env):
    def fail(session):
        raise RuntimeError("simulated commit failure")
    event.listen(Session, "before_commit", fail)
    try:
        assert submit(env, images=[photo()]).status_code == 500
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(env.engine) as s:
        assert s.execute(select(ReturnRequest)).scalars().all() == []
        assert s.execute(select(ReturnEvidence)).scalars().all() == []
        assert s.execute(select(ReturnEvent)).scalars().all() == []
        assert s.execute(select(AdminAuditLog)).scalars().all() == []
    assert env.assets == {} and len(env.deleted) == 1
    assert env.deleted[0][1] is True


def test_admin_filters_pagination_and_return_audit_history(env):
    first, second = create(env), create(env, payload(env, reason="changed_mind"))
    action(env, first["id"], "decision", {"decision": "reject", "note": "Reason for rejection"})
    params = {"reason": "damaged", "status_filter": "rejected", "search": "buyer@returns", "limit": 1}
    result = env.client.get("/api/v1/admin/returns", params=params, headers=env.headers["admin"]).json()
    assert result["total"] == 1 and result["returns"][0]["id"] == first["id"]
    assert result["returns"][0]["customer"]["email"] == "buyer@returns.example"
    result = env.client.get("/api/v1/returns", params={"order_id": str(env.ids["order"]), "page": 2, "limit": 1}, headers=env.headers["buyer"]).json()
    assert result["total"] == 2 and result["total_pages"] == 2 and len(result["returns"]) == 1
    with Session(env.engine) as s:
        audit_rows = s.execute(select(AdminAuditLog).where(AdminAuditLog.entity_id == first["id"])).scalars().all()
        assert {row.action for row in audit_rows} == {"return.requested", "return.rejected"}
        assert audit_rows[-1].after["note"] == "Reason for rejection"


def test_customer_cancellation_behavior_is_preserved(env):
    patch_order(env, status=OrderStatus.CONFIRMED, delivered_at=None)
    response = env.client.post(f"/api/v1/orders/{env.ids['order']}/cancel", headers=env.headers["buyer"], json={"reason": "Changed plans"})
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["refund"]["restocking_fee"]) == Decimal("27.80")
    with Session(env.engine) as s:
        assert s.get(Order, env.ids["order"]).refund_amount == Decimal("528.20")
        assert s.get(ProductVariant, env.ids["variant1"]).stock == 13
        assert s.execute(select(ReturnRequest)).scalars().all() == []
        assert s.execute(select(Refund)).scalar_one().return_request_id is None


def test_full_return_and_late_outbound_rto_cannot_restock_the_purchase(env):
    patch_order(env, shipping_total=Decimal(0), grand_total=Decimal("531"), awb_code="ORIGINAL-OUTBOUND")
    with Session(env.engine) as s:
        payment = s.get(Payment, env.ids["payment"])
        payment.amount = Decimal("531")
        s.add(payment)
        s.commit()
    row = inspected(env, payload(env, items=[{"order_item_id": str(env.ids["item1"]), "quantity": 3},
                                            {"order_item_id": str(env.ids["item2"]), "quantity": 1}]))
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    with Session(env.engine) as s:
        assert s.get(Order, env.ids["order"]).status == OrderStatus.REFUNDED
        webhooks.process_tracking_event(s, {"awb": "ORIGINAL-OUTBOUND", "current_status": "RTO DELIVERED"})
        assert not s.get(Order, env.ids["order"]).stock_released
        assert not s.get(Order, env.ids["order"]).rto_stock_restored
        assert s.get(ProductVariant, env.ids["variant1"]).stock == 10
        assert s.get(ProductVariant, env.ids["variant2"]).stock == 10


def test_real_item_from_another_order_cannot_be_selected(env):
    with Session(env.engine) as s:
        original = s.get(Order, env.ids["order"])
        other = Order(order_number="ANOTHER-ORDER", user_id=env.ids["other"], shipping_address_id=original.shipping_address_id,
            billing_address_id=original.billing_address_id, subtotal=Decimal("100"), grand_total=Decimal("100"))
        s.add(other)
        s.flush()
        item = OrderItem(order_id=other.id, variant_id=env.ids["variant1"], product_name="Other purchase",
            variant_sku="SKU-1", quantity=1, unit_price=Decimal("100"), line_total=Decimal("100"))
        s.add(item)
        s.commit()
        item_id = item.id
    assert submit(env, payload(env, items=[{"order_item_id": str(item_id), "quantity": 1}])).status_code == 422


def test_staff_owned_returns_keep_self_dealing_gate_even_with_sufficient_role_limit(env):
    patch_order(env, user_id=env.ids["manager"], placed_by_staff=True)
    with Session(env.engine) as s:
        role = s.execute(select(Role).where(Role.slug == "manager")).scalar_one()
        role.max_refund_amount = Decimal("5000")
        s.add(role)
        s.commit()
    row = inspected(env, actor="manager_storefront")
    queued = action(env, row["id"], "refund", actor="manager").json()
    assert queued["refund"]["requires_approval"] and env.gateway.calls == 0
    path = f"/api/v1/admin/refunds/{queued['refund']['id']}/approve"
    assert env.client.post(path, headers=env.headers["manager"]).status_code == 400
    assert env.client.post(path, headers=env.headers["admin"]).status_code == 200
    assert env.gateway.calls == 1


def test_current_db_permission_and_active_user_are_checked_after_submission(env):
    row = inspected(env)
    with Session(env.engine) as s:
        actor = s.get(User, env.ids["admin"])
        links = s.execute(select(UserRoleLink).where(UserRoleLink.user_id == actor.id)).scalars().all()
        for link in links:
            s.delete(link)
        s.commit()
    assert action(env, row["id"], "refund").status_code == 403
    with Session(env.engine) as s:
        buyer = s.get(User, env.ids["buyer"])
        buyer.is_active = False
        s.add(buyer)
        s.commit()
    assert env.client.get(f"/api/v1/returns/{row['id']}", headers=env.headers["buyer"]).status_code == 401
    assert env.gateway.calls == 0


def test_direct_return_money_amount_and_approval_limit_cannot_be_bypassed(env):
    row = inspected(env)
    with Session(env.engine) as s:
        order = s.get(Order, env.ids["order"])
        for amount, approver in ((Decimal("556"), env.ids["admin"]), (Decimal("106.20"), env.ids["manager"])):
            with pytest.raises(HTTPException):
                refund_service.process_refund(s, order, OrderStatus.DELIVERED, amount=amount,
                    approved_by=approver, idempotency_key="invalid-direct", return_request_id=UUID(row["id"]))
    assert env.gateway.calls == 0


def test_accepted_provider_refund_then_commit_failure_recovers_without_second_transfer(env):
    row = inspected(env)
    def fail(session):
        raise RuntimeError("Return/refund commit failed")
    event.listen(Session, "before_commit", fail)
    try:
        assert action(env, row["id"], "refund").status_code == 500
    finally:
        event.remove(Session, "before_commit", fail)
    with Session(env.engine) as s:
        request = s.get(ReturnRequest, UUID(row["id"]))
        assert request.status == ReturnStatus.INSPECTION and request.refund_attempts == 0
        assert s.execute(select(Refund)).scalars().all() == []
        assert not s.execute(select(AdminAuditLog).where(AdminAuditLog.action == "return.refunded")).first()
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    assert env.gateway.calls == 1


def test_provider_decline_can_retry_but_does_not_release_physical_quantities(env):
    row = inspected(env, payload(env, qty=3))
    env.gateway.status = "failed"
    response = action(env, row["id"], "refund")
    assert response.status_code == 200 and response.json()["status"] == "inspection", response.text
    assert response.json()["refund"]["status"] == "failed"
    assert submit(env).status_code == 409
    env.gateway.status = "processed"
    assert action(env, row["id"], "refund").json()["status"] == "refunded"
    assert env.gateway.calls == 2


def test_integer_cent_allocation_cannot_overpay_repeated_partial_quantities(env):
    patch_order(env, subtotal=Decimal(".01"), discount_total=Decimal(0), tax_total=Decimal(0),
                shipping_total=Decimal(0), grand_total=Decimal(".01"))
    # Tiny positive value allocated to the first purchased line; zero-value
    # quantities cannot claim money, the full remaining quantity can claim 1 cent.
    with Session(env.engine) as s:
        second = s.get(OrderItem, env.ids["item2"])
        second.line_total = Decimal(0)
        s.add(second)
        payment = s.get(Payment, env.ids["payment"])
        payment.amount = Decimal(".01")
        s.add(payment)
        s.commit()
    assert submit(env).status_code == 409
    row = inspected(env, payload(env, qty=3))
    assert action(env, row["id"], "refund").json()["refund_amount"] == "0.01"
    assert submit(env).status_code == 409


def test_image_pixel_limit_and_legacy_storage_setting_is_ignored(env, monkeypatch):
    from app.services import return_evidence
    monkeypatch.setattr(return_evidence, "MAX_PIXELS", 100)
    assert submit(env, images=[photo()]).status_code == 415
    monkeypatch.setattr(return_evidence, "MAX_PIXELS", 20_000_000)
    monkeypatch.setattr(settings, "RETURN_STORAGE_DIR", str(return_evidence.ROOT / "uploads" / "returns"))
    assert submit(env, images=[photo()]).status_code == 201
    with Session(env.engine) as s:
        assert len(s.execute(select(ReturnRequest)).scalars().all()) == 1


def test_evidence_storage_failure_rolls_back_request_and_audit(env, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("storage unavailable")
    monkeypatch.setattr(service, "upload_image", unavailable)
    assert submit(env, images=[photo()]).status_code == 503
    with Session(env.engine) as s:
        assert s.execute(select(ReturnRequest)).scalars().all() == []
        assert s.execute(select(AdminAuditLog)).scalars().all() == []


def test_reads_do_not_create_audit_events_or_change_request_state(env):
    row = create(env, images=[photo()])
    with Session(env.engine) as s:
        before = {model: len(s.execute(select(model)).scalars().all()) for model in (ReturnEvent, AdminAuditLog, ReturnRequest, ReturnEvidence)}
    for path, actor in (("/api/v1/returns", "buyer"), (f"/api/v1/returns/{row['id']}", "buyer"),
                        (f"/api/v1/orders/{env.ids['order']}/return-eligibility", "buyer"), ("/api/v1/admin/returns", "admin")):
        assert env.client.get(path, headers=env.headers[actor]).status_code == 200
    with Session(env.engine) as s:
        assert before == {model: len(s.execute(select(model)).scalars().all()) for model in before}


def test_postgres_return_refund_replay_moves_money_once(postgres_engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ids, _ = seed(postgres_engine)
    gateway = Gateway()
    monkeypatch.setattr(refund_service, "get_payment_service_for_payment", lambda payment: gateway)
    with Session(postgres_engine) as s:
        actor, admin = s.get(User, ids["buyer"]), s.get(User, ids["admin"])
        row = service.create_request(s, ids["order"], actor, ReturnCreate(idempotency_key=uuid4(), reason="damaged",
            items=[{"order_item_id": ids["item1"], "quantity": 1}]), [], [])
        service.decide(s, row.id, admin, ReturnDecision(decision="approve"))
        service.receive(s, row.id, admin)
        service.inspect(s, row.id, admin, ReturnInspection(passed=True, note="Verified return"))
        s.commit()
        return_id = row.id
    barrier = Barrier(2)
    def refund():
        with Session(postgres_engine) as s:
            actor = s.get(User, ids["admin"])
            s.get(ReturnRequest, return_id)
            barrier.wait(timeout=10)
            row = service.request_refund(s, return_id, actor, ReturnRefundInput())
            s.commit()
            return row.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(refund), pool.submit(refund)]]
    assert results == [ReturnStatus.REFUNDED, ReturnStatus.REFUNDED] and gateway.calls == 1
    with Session(postgres_engine) as s:
        assert len(s.execute(select(Refund)).scalars().all()) == 1
        assert s.get(Order, ids["order"]).refund_amount == Decimal("106.20")


def test_postgres_overlapping_returns_and_replay_reserve_quantity_once(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ids, _ = seed(postgres_engine)
    barrier = Barrier(2)
    def submit_locked(key):
        with Session(postgres_engine) as s:
            actor = s.get(User, ids["buyer"])
            # Prime a stale order before both transactions compete.
            s.get(Order, ids["order"])
            barrier.wait(timeout=10)
            try:
                data = ReturnCreate(idempotency_key=key, reason="damaged", items=[{"order_item_id": ids["item1"], "quantity": 3}])
                row = service.create_request(s, ids["order"], actor, data, [], [])
                s.commit()
                return str(row.id)
            except HTTPException as exc:
                s.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(submit_locked, uuid4()), pool.submit(submit_locked, uuid4())]]
    assert sum(isinstance(result, str) for result in results) == 1 and 409 in results
    with Session(postgres_engine) as s:
        assert sum(item.quantity for item in s.execute(select(ReturnItem)).scalars()) == 3
    # Reuse one key on the remaining item; both transactions replay the same row.
    barrier = Barrier(2)
    key = uuid4()
    def replay():
        with Session(postgres_engine) as s:
            actor = s.get(User, ids["buyer"])
            barrier.wait(timeout=10)
            row = service.create_request(s, ids["order"], actor, ReturnCreate(idempotency_key=key, reason="changed_mind",
                items=[{"order_item_id": ids["item2"], "quantity": 1}]), [], [])
            s.commit()
            return row.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(replay), pool.submit(replay)]]
    assert results[0] == results[1]
