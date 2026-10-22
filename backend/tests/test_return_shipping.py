"""Independent reverse shipping: provider recovery, HTTP grants and stock/money isolation."""
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session

from app.api.v1.admin import returns as admin_returns
from app.models.order import Order, OrderStatus
from app.models.product import ProductVariant
from app.models.product_return import ReturnEvent, ReturnRequest, ReturnStatus, utcnow
from app.models.refund import Refund
from app.models.user import User
from app.core.config import settings
from app.schemas.product_return import ReturnCreate, ReturnDecision
from app.services import product_return, return_shipping
from app.services.shiprocket_service import MockShiprocketService, PickupRequestRejected, RealShiprocketService, ReturnCreationRejected
from tests.test_product_returns import action, create, env, patch_order, payload, seed  # noqa: F401


class Provider(MockShiprocketService):
    def __init__(self):
        self.rows = {}
        self.creates = self.assignments = self.pickups = 0
        self.lost_create = self.lost_awb = self.lost_pickup = self.fail_awb = self.fail_pickup = self.reject = False
        self.hide = False
        self.items = None

    def find_return_order(self, reference):
        return None if self.hide else self.rows.get(reference)

    def get_return_order(self, order_id, reference):
        row = self.rows[reference]
        assert row["order_id"] == order_id
        return row.copy()

    def create_return_order(self, order, reference, items):
        self.creates += 1
        self.items = items
        if self.reject:
            raise ReturnCreationRejected("Shiprocket rejected return creation")
        self.rows[reference] = {"order_id": "RETURN-ORDER-" + reference, "shipment_id": "RETURN-SHIP-" + reference}
        if self.lost_create:
            raise httpx.ReadTimeout("Lost response")
        return self.rows[reference].copy()

    def assign_awb(self, shipment_id, courier_id=None, *, is_return=False):
        assert is_return is True
        self.assignments += 1
        if self.fail_awb:
            raise ValueError("Courier not serviceable")
        result = super().assign_awb(shipment_id, is_return=True)
        row = next(row for row in self.rows.values() if row["shipment_id"] == shipment_id)
        row.update(result)
        if self.lost_awb:
            raise httpx.ReadTimeout("Lost AWB response")
        return result

    def request_pickup(self, shipment_id):
        self.pickups += 1
        if self.fail_pickup:
            raise PickupRequestRejected("Pickup was rejected")
        result = super().request_pickup(shipment_id)
        if self.lost_pickup:
            raise httpx.ReadTimeout("Lost pickup response")
        return result


@pytest.fixture
def provider(monkeypatch):
    instance = Provider()
    monkeypatch.setattr(return_shipping, "get_shipping_service", lambda: instance)
    monkeypatch.setattr(settings, "SHIPPING_PROVIDER", "simulator")
    return instance


def approved(env, quantity=1):
    patch_order(env, shiprocket_order_id="FORWARD-ORDER", shiprocket_shipment_id="FORWARD-SHIP", awb_code="FORWARD-AWB",
                courier_name="Forward Courier", shipment_status="DELIVERED", tracking_data=[{"status": "DELIVERED"}])
    row = create(env, payload(env, qty=quantity))
    assert action(env, row["id"], "decision", {"decision": "approve"}).status_code == 200
    return row["id"]


def unchanged_forward(env):
    with Session(env.engine) as session:
        order = session.get(Order, env.ids["order"])
        assert (order.shiprocket_order_id, order.shiprocket_shipment_id, order.awb_code, order.courier_name) == (
            "FORWARD-ORDER", "FORWARD-SHIP", "FORWARD-AWB", "Forward Courier")
        assert order.status == OrderStatus.DELIVERED and order.shipment_status == "DELIVERED"
        assert order.tracking_data == [{"status": "DELIVERED"}]
        assert order.refund_amount == Decimal("0") and not order.stock_released
        assert session.get(ProductVariant, env.ids["variant1"]).stock == 10
        assert not session.execute(select(Refund)).scalars().all()


def test_create_and_repeated_clicks_use_selected_items_and_preserve_forward_shipment(env, provider):
    return_id = approved(env, 2)
    first = action(env, return_id, "shipping/shiprocket")
    assert first.status_code == 200, first.text
    row = first.json()
    assert row["status"] == "approved" and row["tracking_provider"] == "shiprocket"
    assert len(row["shipping_reference"]) == 20 and row["shipping_reference"].isdigit()
    assert row["shiprocket_order_id"] != "FORWARD-ORDER" and row["tracking_number"] != "FORWARD-AWB"
    assert provider.items == [{"name": "Purchased product 1", "sku": "SKU-1", "units": 2, "selling_price": "100.00", "discount": "0", "hsn": ""}]
    pickup = action(env, return_id, "shipping/simulator/trigger-event", {"event": "picked_up"})
    assert pickup.status_code == 200 and pickup.json()["return_status"] == "return_shipped"
    for _ in range(3):
        assert action(env, return_id, "shipping/shiprocket").json()["tracking_number"] == row["tracking_number"]
    assert (provider.creates, provider.assignments, provider.pickups) == (1, 1, 1)
    unchanged_forward(env)


@pytest.mark.parametrize("actor", ["buyer", "other", "staff", "admin_storefront"])
def test_creation_is_permission_and_admin_audience_gated(env, provider, actor):
    return_id = approved(env)
    assert action(env, return_id, "shipping/shiprocket", actor=actor).status_code == 403
    assert provider.creates == provider.assignments == 0


def test_creation_requires_approval_and_manual_tracking_remains_available(env, provider):
    row = create(env)
    assert action(env, row["id"], "shipping/shiprocket").status_code == 409
    assert action(env, row["id"], "decision", {"decision": "approve"}).status_code == 200
    assert action(env, row["id"], "tracking", {"tracking_number": "OTHER-AWB", "courier_name": "Other courier"}).status_code == 200
    assert action(env, row["id"], "shipping/shiprocket").status_code == 409
    assert provider.creates == 0


def test_multiple_partial_returns_have_distinct_reverse_shipments(env, provider):
    first = action(env, approved(env), "shipping/shiprocket").json()
    second = action(env, approved(env), "shipping/shiprocket").json()
    for field in ("shipping_reference", "shiprocket_order_id", "shiprocket_shipment_id", "tracking_number"):
        assert first[field] != second[field]
    assert provider.creates == provider.assignments == provider.pickups == 2
    unchanged_forward(env)


def test_default_simulator_books_an_independent_return_with_stable_identifiers(env, monkeypatch):
    monkeypatch.setattr(settings, "SHIPPING_PROVIDER", "simulator")
    return_id = approved(env)
    first = action(env, return_id, "shipping/shiprocket")
    assert first.status_code == 200, first.text
    row = first.json()
    assert row["shiprocket_order_id"].startswith("SR-RET-") and row["shiprocket_shipment_id"].startswith("SR-RET-SHP-")
    assert action(env, return_id, "shipping/shiprocket").json()["tracking_number"] == row["tracking_number"]
    unchanged_forward(env)


def test_lookup_failure_does_not_claim_or_post_a_shipment(env, provider, monkeypatch):
    return_id = approved(env)
    def fail(reference):
        raise httpx.ReadTimeout("Lookup unavailable")
    monkeypatch.setattr(provider, "find_return_order", fail)
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.shipping_requested_at is None and row.shiprocket_order_id is None
    assert provider.creates == 0


def test_provider_cannot_attach_the_original_forward_awb_to_a_return(env, provider, monkeypatch):
    return_id = approved(env)
    monkeypatch.setattr(provider, "assign_awb", lambda *args, **kwargs: {"awb_code": "FORWARD-AWB", "courier_name": "Forward Courier"})
    assert action(env, return_id, "shipping/shiprocket").status_code == 409
    with Session(env.engine) as session:
        assert session.get(ReturnRequest, UUID(return_id)).tracking_number is None
    unchanged_forward(env)


def test_lost_creation_response_is_recovered_by_reference_without_second_post(env, provider):
    return_id = approved(env)
    provider.lost_create = True
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.shipping_requested_at and row.shipping_reference and not row.shiprocket_order_id
    result = action(env, return_id, "shipping/shiprocket")
    assert result.status_code == 200, result.text
    assert (provider.creates, provider.assignments) == (1, 1)
    unchanged_forward(env)


def test_unresolved_creation_never_blindly_reposts_or_allows_manual_fork(env, provider):
    return_id = approved(env)
    provider.lost_create = provider.hide = True
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    assert action(env, return_id, "shipping/shiprocket").status_code == 409
    assert action(env, return_id, "tracking", {"tracking_number": "OTHER-AWB", "courier_name": "Other"}).status_code == 409
    assert provider.creates == 1
    provider.hide = False
    assert action(env, return_id, "shipping/shiprocket").status_code == 200


def test_definite_rejection_allows_safe_retry_of_same_reference(env, provider):
    return_id = approved(env)
    provider.reject = True
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.shipping_requested_at is None
        reference = row.shipping_reference
    provider.reject = False
    result = action(env, return_id, "shipping/shiprocket")
    assert result.status_code == 200 and result.json()["shipping_reference"] == reference
    assert provider.creates == 2 and len(provider.rows) == 1


def test_pickup_rejection_retries_without_recreating_reverse_shipment(env, provider):
    return_id = approved(env)
    provider.fail_pickup = True
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.tracking_number and row.pickup_requested_at is None and row.status == ReturnStatus.APPROVED
    provider.fail_pickup = False
    assert action(env, return_id, "shipping/shiprocket").status_code == 200
    assert (provider.creates, provider.assignments, provider.pickups) == (1, 1, 2)


def test_lost_pickup_response_is_checkpointed_without_duplicate_request(env, provider):
    return_id = approved(env)
    provider.lost_pickup = True
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.tracking_number and row.pickup_requested_at is not None and row.status == ReturnStatus.APPROVED
    provider.lost_pickup = False
    assert action(env, return_id, "shipping/shiprocket").status_code == 200
    assert provider.pickups == 1


@pytest.mark.parametrize("event", ["shipping_creation_requested", "shipping_created", "tracking_attached", "pickup_request_started", "pickup_requested"])
def test_failed_checkpoint_or_final_commit_is_retry_safe(env, provider, monkeypatch, event):
    return_id = approved(env)
    original = Session.commit
    failed = []
    def fail_once(session):
        if not failed and session.execute(select(ReturnEvent.id).where(ReturnEvent.return_id == UUID(return_id), ReturnEvent.action == event)).first():
            failed.append(True)
            raise RuntimeError("Commit failed")
        return original(session)
    monkeypatch.setattr(Session, "commit", fail_once)
    assert action(env, return_id, "shipping/shiprocket").status_code == 500
    assert failed
    assert action(env, return_id, "shipping/shiprocket").status_code == 200
    assert provider.creates == provider.assignments == provider.pickups == 1
    unchanged_forward(env)


@pytest.mark.parametrize("lost", [False, True])
def test_awb_failure_preserves_reverse_ids_and_resumes_without_recreation(env, provider, lost):
    return_id = approved(env)
    provider.lost_awb, provider.fail_awb = lost, not lost
    assert action(env, return_id, "shipping/shiprocket").status_code == 502
    with Session(env.engine) as session:
        row = session.get(ReturnRequest, UUID(return_id))
        assert row.shiprocket_order_id and row.shiprocket_shipment_id and not row.tracking_number
    provider.fail_awb = provider.lost_awb = False
    assert action(env, return_id, "shipping/shiprocket").status_code == 200
    assert provider.creates == 1 and provider.assignments == (1 if lost else 2) and provider.pickups == 1


def test_reverse_simulator_and_sync_receive_only_without_forward_stock_or_money_changes(env, provider, monkeypatch):
    return_id = approved(env)
    row = action(env, return_id, "shipping/shiprocket").json()
    listing = env.client.get('/api/v1/admin/returns/shipping/simulator/shipments', headers=env.headers["admin"])
    assert listing.status_code == 200
    shipment = listing.json()["shipments"][0]
    assert shipment["shipment_type"] == "return" and shipment["return_id"] == return_id
    assert shipment["awb_code"] == row["tracking_number"]
    assert shipment["reason_label"] == "Damaged product"
    assert shipment["items"] == [{"product_name": "Purchased product 1", "quantity": 1}]
    path = "shipping/simulator/trigger-event"
    assert action(env, return_id, path, {"event": "rto_delivered"}).status_code == 422
    expected_labels = {
        "picked_up": "RETURN PICKED UP", "in_transit": "RETURN IN TRANSIT",
        "out_for_delivery": "RETURN OUT FOR DELIVERY", "delivered": "RETURN DELIVERED",
    }
    for event in ("picked_up", "in_transit", "out_for_delivery", "delivered", "in_transit"):
        result = action(env, return_id, path, {"event": event})
        assert result.status_code == 200, result.text
        assert result.json()["simulated_payload"]["data"]["awb"] == row["tracking_number"]
        assert result.json()["simulated_payload"]["data"]["is_return"] == 1
        assert result.json()["simulated_payload"]["data"]["current_status"] == expected_labels[event]
        assert result.json()["effects"]["forward_awb_preserved"] is True
    assert result.json()["return_status"] == "received"
    assert result.json()["effects"]["inspection_unchanged"] is True
    assert result.json()["effects"]["refund_unchanged"] is True
    detail = env.client.get(f'/api/v1/admin/returns/{return_id}', headers=env.headers["admin"]).json()
    assert detail["received_at"] and detail["inspection_passed"] is None and detail["refund"] is None
    monkeypatch.setattr(admin_returns, "get_shipping_service", lambda: provider)
    seen = []
    def tracking(awb):
        seen.append(awb)
        return {"tracking_data": {"shipment_track_activities": [{"sr-status-label": "DELIVERED", "date": "2026-10-05", "location": {"name": "Warehouse"}}]}}
    monkeypatch.setattr(provider, "get_tracking", tracking)
    assert action(env, return_id, "tracking/sync").json()["status"] == "received"
    assert seen == [row["tracking_number"]]
    assert action(env, return_id, "shipping/shiprocket").json()["status"] == "received"
    monkeypatch.setattr(settings, "SHIPPING_PROVIDER", "shiprocket")
    assert action(env, return_id, path, {"event": "delivered"}).status_code == 409
    unchanged_forward(env)


def test_simulator_shows_and_tracks_manually_attached_shiprocket_returns(env, provider):
    return_id = approved(env, 2)
    response = action(env, return_id, "tracking", {"tracking_number": "ATTACHED-RETURN-AWB",
                      "courier_name": "Reverse courier", "provider": "shiprocket"})
    assert response.status_code == 200, response.text
    assert response.json()["shiprocket_order_id"] is None
    listing = env.client.get('/api/v1/admin/returns/shipping/simulator/shipments', headers=env.headers["admin"])
    assert listing.status_code == 200, listing.text
    shipment = listing.json()["shipments"][0]
    assert shipment["return_id"] == return_id and shipment["awb_code"] == "ATTACHED-RETURN-AWB"
    assert shipment["shiprocket_order_id"] is None and shipment["shiprocket_shipment_id"] is None
    assert shipment["items"] == [{"product_name": "Purchased product 1", "quantity": 2}]
    delivered = action(env, return_id, "shipping/simulator/trigger-event", {"event": "delivered"})
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["return_status"] == "received"
    assert delivered.json()["simulated_payload"]["data"]["awb"] == "ATTACHED-RETURN-AWB"
    assert provider.creates == provider.assignments == 0
    unchanged_forward(env)


def test_simulator_return_listing_excludes_unbooked_and_other_carriers_and_checks_grants(env, provider):
    unbooked = approved(env)
    manual = approved(env)
    assert action(env, manual, "tracking", {"tracking_number": "OTHER-COURIER-AWB", "courier_name": "Other"}).status_code == 200
    managed = approved(env)
    assert action(env, managed, "tracking", {"tracking_number": "SHIPROCKET-RETURN-AWB", "courier_name": "Shiprocket", "provider": "shiprocket"}).status_code == 200
    listing = env.client.get('/api/v1/admin/returns/shipping/simulator/shipments', headers=env.headers["admin"])
    assert listing.status_code == 200, listing.text
    assert [row["return_id"] for row in listing.json()["shipments"]] == [managed]
    assert action(env, unbooked, "shipping/simulator/trigger-event", {"event": "delivered"}).status_code == 409
    assert action(env, manual, "shipping/simulator/trigger-event", {"event": "delivered"}).status_code == 409
    for actor in ("buyer", "staff", "admin_storefront"):
        assert env.client.get('/api/v1/admin/returns/shipping/simulator/shipments', headers=env.headers[actor]).status_code == 403
    assert provider.creates == provider.assignments == 0
    unchanged_forward(env)


def test_live_service_uses_documented_return_and_awb_contracts(env, monkeypatch):
    return_id = approved(env, 2)
    service = RealShiprocketService()
    service._cached_token, service._token_expiry = "test-token", utcnow() + timedelta(days=1)
    monkeypatch.setattr(return_shipping, "get_shipping_service", lambda: service)
    monkeypatch.setattr(settings, "SHIPROCKET_PICKUP_LOCATION", "Warehouse")
    calls = []
    reference = "9" + str(UUID(return_id).int % (10 ** 19)).zfill(19)
    def get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        if url.endswith('/orders'):
            data = {"data": [], "meta": {"pagination": {"total_pages": 1}}}
        elif url.endswith('/settings/company/pickup'):
            data = {"data": {"shipping_address": [{"id": 123, "pickup_location": "Warehouse", "status": 1,
                "name": "Seller", "address": "Warehouse Road", "city": "Delhi", "state": "Delhi", "country": "India",
                "pin_code": "110002", "email": "warehouse@example.com", "phone": "9999999999"}]}}
        else:
            assert url.endswith('/orders/show/1001')
            data = {"data": {"id": 1001, "channel_order_id": reference, "is_return": 1,
                             "shipments": {"id": 1002, "awb": "", "courier": ""}}}
        return httpx.Response(200, json=data, request=httpx.Request("GET", url))
    def post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        data = {"order_id": 1001, "shipment_id": 1002, "status": "RETURN PENDING"} if url.endswith('/orders/create/return') else {
            "response": {"data": {"awb_code": "RETURN-LIVE-AWB", "courier_name": "Reverse Courier"}}}
        return httpx.Response(200, json=data, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(httpx, "post", post)
    result = action(env, return_id, "shipping/shiprocket")
    assert result.status_code == 200, result.text
    posts = [(url, args["json"]) for method, url, args in calls if method == "POST"]
    assert [url.rsplit('/external/', 1)[1] for url, _ in posts] == ['orders/create/return', 'courier/assign/awb', 'courier/generate/pickup']
    booking = posts[0][1]
    assert booking["pickup_address"] == "Street" and booking["shipping_address"] == "Warehouse Road"
    assert booking["pickup_location_id"] == "" and booking["payment_method"] == "Prepaid"
    assert booking["order_items"][0]["name"] == "Purchased product 1" and booking["order_items"][0]["units"] == 2
    assert booking["weight"] == 0.5 and booking["length"] == booking["breadth"] == booking["height"] == 10
    assert posts[1][1] == {"shipment_id": "1002", "is_return": 1}
    assert posts[2][1] == {"shipment_id": ["1002"]}
    assert calls[0][2]["params"]["search"] == reference
    unchanged_forward(env)


@pytest.mark.parametrize("bad", ["forward", "duplicate", "incomplete"])
def test_live_lookup_rejects_ambiguous_forward_and_invalid_responses(monkeypatch, bad):
    service = RealShiprocketService()
    def lookup(path, **params):
        if path == 'orders':
            return {"data": [{"id": 1, "channel_order_id": "ref"}] * (2 if bad == 'duplicate' else 1)}
        return {"data": {"id": 1, "channel_order_id": "ref", "is_return": 0 if bad == 'forward' else 1,
                         "shipments": {} if bad == 'incomplete' else {"id": 2}}}
    monkeypatch.setattr(service, "_return_get", lookup)
    with pytest.raises(ValueError):
        service.find_return_order('ref')


def test_postgres_concurrent_return_booking_creates_and_assigns_once(postgres_engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ids, _ = seed(postgres_engine)
    provider = Provider()
    monkeypatch.setattr(return_shipping, "get_shipping_service", lambda: provider)
    with Session(postgres_engine) as session:
        row = product_return.create_request(session, ids["order"], session.get(User, ids["buyer"]),
            ReturnCreate(idempotency_key=uuid4(), reason="damaged", items=[{"order_item_id": ids["item1"], "quantity": 1}]), [], [])
        product_return.decide(session, row.id, session.get(User, ids["admin"]), ReturnDecision(decision="approve"))
        session.commit()
        return_id = row.id
    barrier = Barrier(3)
    def book():
        with Session(postgres_engine) as session:
            actor = session.get(User, ids["admin"])
            session.get(ReturnRequest, return_id)
            barrier.wait(timeout=10)
            try:
                row = return_shipping.create_shipment(session, return_id, actor)
                session.commit()
                return row.tracking_number
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(book) for _ in range(3)]
        results = [future.result(timeout=30) for future in futures]
    assert provider.creates == provider.assignments == 1
    assert len({result for result in results if isinstance(result, str)}) == 1
    assert all(isinstance(result, str) or result == 409 for result in results)
    with Session(postgres_engine) as session:
        row = return_shipping.create_shipment(session, return_id, session.get(User, ids["admin"]))
        assert row.status == ReturnStatus.APPROVED and row.tracking_number
