# tests/test_guardrails.py
"""Money-movement guardrails: unified cancel, approvals, idempotency,
self-dealing block, invites, audit log, promo targeting, coupon hygiene.

Isolated sqlite file DB via dependency_overrides. PSP + mailer mocked.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES

settings.ENVIRONMENT = "test"

from app.api.deps import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.address import Address  # noqa: E402
from app.models.order import Order, OrderStatus  # noqa: E402
from app.models.payment import Payment, PaymentStatus, PaymentProvider  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.refund import Refund  # noqa: E402
from app.models.staff_invite import StaffInvite  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402
from app.repositories import notification as notification_repo  # noqa: E402
from app.services import otp_service  # noqa: E402
from app.services import refund_service  # noqa: E402
from app.utils.coupon import validate_coupon  # noqa: E402
from app.models.coupon import Coupon  # noqa: E402

TEST_DB = "/tmp/guardrails_test.db"
PASSWORD = "TestPass123"
FIXED_CODE = "123456"

_fake_psp = None
_admin_headers: dict = {}
_manager_headers: dict = {}
_ids: dict = {}


class FakePSP:
    def __init__(self):
        self.calls = 0
        self.fail_next_with = None
        self.provider_state = None

    def create_refund(self, payment_id, amount, notes=None):
        self.calls += 1
        if self.fail_next_with is not None:
            err, self.fail_next_with = self.fail_next_with, None
            return {"status": "failed", "error": err}
        return {"status": "processed", "refund_id": f"rfnd_test_{self.calls}"}

    def get_charge_refund_state(self, payment_id):
        return self.provider_state


def _seed(session: Session) -> None:
    for key, label, module, description in PERMISSIONS:
        session.add(
            Permission(key=key, label=label, module=module, description=description)
        )
    session.flush()
    perms = {p.key: p for p in session.execute(select(Permission)).scalars().all()}
    limits = {"admin": None, "manager": Decimal("5000"), "staff": Decimal("0"), "customer": Decimal("0")}
    for slug, spec in SYSTEM_ROLES.items():
        role = Role(
            name=spec["name"], slug=slug, description=spec["description"],
            is_system=True, max_refund_amount=limits[slug],
        )
        session.add(role)
        session.flush()
        for key in spec["permissions"]:
            session.add(RolePermissionLink(role_id=role.id, permission_id=perms[key].id))
    session.commit()


def _make_user(session: Session, email: str, legacy: UserRole, slug: str) -> User:
    user = User(
        email=email, username=f"u_{uuid4().hex[:8]}",
        password_hash=hash_password(PASSWORD), role=legacy,
        full_name=email, is_active=True, email_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    role = rbac_repo.get_role_by_slug(session, slug)
    rbac_repo.set_user_roles(session, user, [role])
    return user


def _make_address(session: Session, user: User) -> Address:
    addr = Address(
        user_id=user.id, label="Home", line1="1 Main St", city="Mumbai",
        state="MH", postal_code="400001", country="IN", is_default=True,
    )
    session.add(addr)
    session.commit()
    session.refresh(addr)
    return addr


def _make_order(session: Session, user: User, addr: Address, total: str,
                staff: bool = False) -> Order:
    order = Order(
        order_number=f"ORD-G-{uuid4().hex[:8]}", user_id=user.id,
        shipping_address_id=addr.id, billing_address_id=addr.id,
        subtotal=Decimal(total), discount_total=Decimal("0"),
        tax_total=Decimal("0"), shipping_total=Decimal("0"),
        grand_total=Decimal(total), payment_method="online",
        payment_status="paid", status=OrderStatus.CONFIRMED,
        placed_by_staff=staff,
        placed_at=datetime.now(timezone.utc),
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    payment = Payment(
        order_id=order.id, provider=PaymentProvider.RAZORPAY,
        provider_payment_id=f"order_{uuid4().hex[:8]}",
        provider_payment_intent=f"pay_{uuid4().hex[:8]}",
        amount=Decimal(total), currency="INR",
        status=PaymentStatus.SUCCEEDED,
    )
    session.add(payment)
    session.commit()
    return order


@pytest.fixture(scope="module")
def client():
    global _fake_psp
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(
        bind=test_engine, class_=Session, expire_on_commit=False
    )
    with TestingSession() as s:
        _seed(s)
        admin = _make_user(s, "owner@g-test.com", UserRole.admin, "admin")
        manager = _make_user(s, "mgr@g-test.com", UserRole.manager, "manager")
        shopper = _make_user(s, "buyer@g-test.com", UserRole.customer, "customer")
        admin_addr = _make_address(s, admin)
        mgr_addr = _make_address(s, manager)
        shop_addr = _make_address(s, shopper)
        _ids["admin"] = str(admin.id)
        _ids["manager"] = str(manager.id)
        _ids["shopper"] = str(shopper.id)
        _ids["shopper_addr"] = str(shop_addr.id)
        # Small paid order (within manager authority) + big one (approval).
        _ids["small_order"] = str(_make_order(s, shopper, shop_addr, "1230.00").id)
        _ids["big_order"] = str(_make_order(s, shopper, shop_addr, "20000.00").id)
        # Staff-placed order owned by the manager (self-dealing case).
        _ids["self_order"] = str(
            _make_order(s, manager, mgr_addr, "900.00", staff=True).id
        )
        _ids["admin_addr"] = str(admin_addr.id)

    _fake_psp = FakePSP()
    p_psp = mock.patch.object(
        refund_service, "get_payment_service_for_payment", return_value=_fake_psp
    )
    p_code = mock.patch.object(otp_service, "generate_otp", return_value=FIXED_CODE)
    p_mail = mock.patch.object(
        otp_service.email_service, "send_email", return_value=True
    )
    p_psp.start()
    p_code.start()
    p_mail.start()

    def override_session():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    limiter._storage.reset()
    try:
        with TestClient(app) as c:
            for email, store in (
                ("owner@g-test.com", _admin_headers),
                ("mgr@g-test.com", _manager_headers),
            ):
                resp = c.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": PASSWORD},
                )
                assert resp.status_code == 200, resp.text
                body = resp.json()
                assert body.get("otp_required") is True
                verify = c.post(
                    "/api/v1/auth/login/verify-otp",
                    json={"challenge_token": body["challenge_token"],
                          "otp_code": FIXED_CODE},
                )
                assert verify.status_code == 200, verify.text
                store["Authorization"] = f"Bearer {verify.json()['access_token']}"
            yield c
    finally:
        app.dependency_overrides.clear()
        p_mail.stop()
        p_code.stop()
        p_psp.stop()


def _testing_session():
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    TestingSession = sessionmaker(
        bind=test_engine, class_=Session, expire_on_commit=False
    )
    return TestingSession()


# ---------- Unified cancel: auto-refund within authority ----------

def test_admin_cancel_paid_auto_refunds_within_authority(client):
    calls_before = _fake_psp.calls
    resp = client.post(
        f"/api/v1/admin/orders/{_ids['small_order']}/cancel",
        json={"reason": "Out of stock", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "refunded"
    assert body["refund"]["processed"] is True
    assert body["refund"].get("requires_approval") is False
    assert _fake_psp.calls == calls_before + 1
    # Ledger row exists.
    rows = client.get("/api/v1/admin/refunds", headers=_manager_headers).json()
    assert rows["total"] >= 1
    assert any(
        r["status"] == "executed" and r["reason"] == "Out of stock"
        for r in rows["refunds"]
    )


def test_admin_cancel_refund_later_moves_no_money(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "500.00")
        order_id = str(order.id)
    calls_before = _fake_psp.calls
    resp = client.post(
        f"/api/v1/admin/orders/{order_id}/cancel",
        json={"reason": "Customer asked to wait", "refund_choice": "later"},
        headers=_manager_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"
    assert resp.json()["refund"]["processed"] is False
    assert _fake_psp.calls == calls_before


def test_admin_cancel_requires_reason(client):
    resp = client.post(
        f"/api/v1/admin/orders/{_ids['big_order']}/cancel",
        json={"reason": "  ", "refund_choice": "later"},
        headers=_manager_headers,
    )
    assert resp.status_code == 422, resp.text


# ---------- Approval flow: above limit + self-dealing ----------

def test_above_limit_stages_approval_then_admin_executes(client):
    calls_before = _fake_psp.calls
    resp = client.post(
        f"/api/v1/admin/orders/{_ids['big_order']}/cancel",
        json={"reason": "Fraud suspected", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["refund"].get("requires_approval") is True
    assert _fake_psp.calls == calls_before  # no money moved yet
    row_id = resp.json()["refund"]["refund_row_id"]

    # The requesting manager cannot self-approve.
    denied = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=_manager_headers
    )
    assert denied.status_code == 400, denied.text

    # A different admin approves → PSP fires exactly once.
    approved = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=_admin_headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["processed"] is True
    assert _fake_psp.calls == calls_before + 1

    # Re-approving the settled row is rejected.
    again = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=_admin_headers
    )
    assert again.status_code == 400, again.text


def test_self_dealing_requires_second_admin(client):
    resp = client.post(
        f"/api/v1/admin/orders/{_ids['self_order']}/cancel",
        json={"reason": "Changed mind", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert resp.status_code == 200, resp.text
    # ₹900 is within the ₹5000 limit — but the manager owns this order.
    assert resp.json()["refund"].get("requires_approval") is True
    row_id = resp.json()["refund"]["refund_row_id"]
    approved = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=_admin_headers
    )
    assert approved.status_code == 200, approved.text


def test_reject_moves_no_money(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "30000.00")
        order_id = str(order.id)
    calls_before = _fake_psp.calls
    staged = client.post(
        f"/api/v1/admin/orders/{order_id}/cancel",
        json={"reason": "Review first", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert staged.json()["refund"].get("requires_approval") is True
    row_id = staged.json()["refund"]["refund_row_id"]
    rejected = client.post(
        f"/api/v1/admin/refunds/{row_id}/reject",
        json={"note": "Customer confirmed keep"},
        headers=_admin_headers,
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert _fake_psp.calls == calls_before


# ---------- Service-level: idempotency + balance cap ----------

def test_idempotent_replay_no_second_psp_call(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "1000.00")
        calls_before = _fake_psp.calls
        first = refund_service.process_refund(
            s, order, order.status, reason="t1",
            requested_by=shopper.id, idempotency_key=f"test-{uuid4().hex}",
        )
        assert first["processed"] is True
        # Same key again (retry/double-click) → replay, no PSP call.
        key = s.get(Refund, UUID(first["refund_row_id"])).idempotency_key
        second = refund_service.process_refund(
            s, order, order.status, reason="t1-retry",
            requested_by=shopper.id, idempotency_key=key,
        )
        assert second.get("duplicate") is True
        assert second["processed"] is True
        assert _fake_psp.calls == calls_before + 1


# ---------- Invites ----------

def test_staff_invite_create_rules(client):
    created = client.post(
        "/api/v1/admin/invites",
        json={"email": "newhire@g-test.com", "role_slugs": ["staff"]},
        headers=_admin_headers,
    )
    assert created.status_code == 201, created.text

    pending = client.get("/api/v1/admin/invites", headers=_admin_headers).json()
    assert any(
        i["email"] == "newhire@g-test.com" and i["status"] == "pending"
        for i in pending
    )

    # Duplicate pending invite rejected.
    dup = client.post(
        "/api/v1/admin/invites",
        json={"email": "newhire@g-test.com", "role_slugs": ["staff"]},
        headers=_admin_headers,
    )
    assert dup.status_code == 400, dup.text

    # Unknown role rejected.
    bad = client.post(
        "/api/v1/admin/invites",
        json={"email": "ghost@g-test.com", "role_slugs": ["nope"]},
        headers=_admin_headers,
    )
    assert bad.status_code == 400, bad.text

    # Manager lacks users.manage_roles → forbidden.
    forbidden = client.post(
        "/api/v1/admin/invites",
        json={"email": "other@g-test.com", "role_slugs": ["staff"]},
        headers=_manager_headers,
    )
    assert forbidden.status_code == 403, forbidden.text


def test_staff_invite_accept_new_account(client):
    import hashlib

    # Seed a known-token invite directly (the emailed token is opaque).
    token = "accept-me-" + uuid4().hex
    with _testing_session() as s:
        invite = StaffInvite(
            email="joiner@g-test.com", role_slugs=["staff"],
            invited_by=UUID(_ids["admin"]),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        s.add(invite)
        s.commit()

    preview = client.get(
        "/api/v1/invites/accept", params={"token": token}
    ).json()
    assert preview["valid"] is True
    assert preview["email"] == "joiner@g-test.com"
    assert preview["role_slugs"] == ["staff"]

    accepted = client.post(
        "/api/v1/invites/accept",
        json={"token": token, "username": "joiner1",
              "password": "JoinerPass123"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["access_token"]

    # New staffer can log in (OTP challenge) and holds staff perms.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "joiner@g-test.com", "password": "JoinerPass123"},
    )
    assert login.json().get("otp_required") is True

    # Single-use: second accept fails.
    again = client.post(
        "/api/v1/invites/accept",
        json={"token": token, "username": "joiner2",
              "password": "JoinerPass123"},
    )
    assert again.status_code == 400, again.text


# ---------- Audit log ----------

def test_audit_log_records_privileged_actions(client):
    resp = client.get(
        "/api/v1/admin/audit-log", params={"limit": 50},
        headers=_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    actions = {e["action"] for e in resp.json()["entries"]}
    assert "order.cancelled" in actions
    assert "refund.executed" in actions or "refund.approved" in actions
    assert "invite.created" in actions
    # Manager holds reports.view (auditors need the log) → allowed.
    allowed = client.get("/api/v1/admin/audit-log", headers=_manager_headers)
    assert allowed.status_code == 200, allowed.text


# ---------- Promo targeting + audiences (repo-level) ----------

def test_promo_reaches_only_permissionless_users():
    with _testing_session() as s:
        _, count = notification_repo.broadcast_promotion(
            s, title="t", message="m"
        )
        from app.models.notification import Notification
        rows = s.execute(select(Notification).where(
            Notification.title == "t")).scalars().all()
        user_ids = {r.user_id for r in rows}
        from app.models.user import User as U
        users = {u.id: u.email for u in s.execute(select(U)).scalars().all()}
        emails = {users[i] for i in user_ids}
        assert "buyer@g-test.com" in emails
        assert "owner@g-test.com" not in emails
        assert "mgr@g-test.com" not in emails
        assert count == len(rows) >= 1


def test_notification_audience_split():
    with _testing_session() as s:
        from app.models.user import User as U
        owner = s.execute(
            select(U).where(U.email == "owner@g-test.com")).scalars().one()
        buyer = s.execute(
            select(U).where(U.email == "buyer@g-test.com")).scalars().one()
        notification_repo.notify_admins_order_placed(
            s, _make_order(
                s, buyer,
                s.get(Address, UUID(_ids["shopper_addr"])),
                "700.00",
            ),
        )
        s.commit()
        shopper_items, _, _ = notification_repo.list_for_user(
            s, owner.id, audience="shopper")
        staff_items, _, staff_unread = notification_repo.list_for_user(
            s, owner.id, audience="staff")
        # The admin alert is staff-only; promos/order-status are shopper-only.
        assert all(r.type.value != "order_placed" for r in shopper_items)
        assert any(r.type.value == "order_placed" for r in staff_items)
        assert staff_unread >= 1


# ---------- Refund authority limits (unit) ----------

def test_effective_refund_limit_resolution():
    with _testing_session() as s:
        from app.models.user import User as U
        admin = s.execute(select(U).where(U.email == "owner@g-test.com")).scalars().one()
        manager = s.execute(select(U).where(U.email == "mgr@g-test.com")).scalars().one()
        shopper = s.execute(select(U).where(U.email == "buyer@g-test.com")).scalars().one()
        # Admin: unlimited (NULL limit on the role).
        assert refund_service.effective_refund_limit(s, admin) is None
        # Manager: catalog limit.
        assert refund_service.effective_refund_limit(s, manager) == Decimal("5000")
        # Shopper: zero.
        assert refund_service.effective_refund_limit(s, shopper) == Decimal("0")
        # Stacking a read-only role never lowers the ceiling.
        customer_role = rbac_repo.get_role_by_slug(s, "customer")
        rbac_repo.set_user_roles(s, manager, [
            rbac_repo.get_role_by_slug(s, "manager"), customer_role])
        assert refund_service.effective_refund_limit(s, manager) == Decimal("5000")


# ---------- Attention queue: money held with no refund in flight ----------

def test_attention_queue_lists_unrefunded_paid_cancels(client):
    body = client.get(
        "/api/v1/admin/refunds/attention", headers=_manager_headers
    )
    assert body.status_code == 200, body.text
    orders = body.json()["orders"]
    # The 30k rejected-cancel order from test_reject_moves_no_money sits
    # cancelled + paid + unrefunded with no pending row → must surface.
    assert any(
        o["remaining"] > 0 and o["status"] == "cancelled" for o in orders
    ), orders
    for o in body.json()["orders"]:
        assert o["remaining"] > 0


def test_attention_queue_excludes_cod_unpaid_and_pending(client):
    # COD cancelled order → never appears (no captured money).
    # Delivered paid order → never appears either (no action needed; the
    # Issue Refund button on the order remains the on-demand path).
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        cod = _make_order(s, shopper, addr, "600.00")
        from app.models.order import OrderStatus as OS
        cod.payment_method = "cod"
        cod.payment_status = "cod_pending"
        cod.status = OS.CANCELLED
        s.add(cod)
        delivered = _make_order(s, shopper, addr, "874.82")
        delivered.status = OS.DELIVERED
        s.add(delivered)
        s.commit()
        cod_number = cod.order_number
        delivered_number = delivered.order_number
    body = client.get(
        "/api/v1/admin/refunds/attention", headers=_manager_headers
    ).json()
    numbers = [o["order_number"] for o in body["orders"]]
    assert cod_number not in numbers
    assert delivered_number not in numbers
    # Manager lacks nothing here (orders.refund held) — customer forbidden.
    # (Customer has no perms; use an unauthenticated call instead.)
    anon = client.get("/api/v1/admin/refunds/attention")
    assert anon.status_code in (401, 403), anon.status_code


# ---------- Status endpoint can no longer move money ----------

def test_my_authority_endpoint(client):
    mgr = client.get(
        "/api/v1/admin/refunds/my-authority", headers=_manager_headers
    )
    assert mgr.status_code == 200, mgr.text
    assert mgr.json() == {"max_refund_amount": "5000.00", "unlimited": False}
    adm = client.get(
        "/api/v1/admin/refunds/my-authority", headers=_admin_headers
    )
    assert adm.json() == {"max_refund_amount": None, "unlimited": True}


def test_second_manager_cannot_approve_above_own_limit(client):    # Fresh above-limit pending row requested by mgr.
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "25000.00")
        order_id = str(order.id)
        _make_user(s, "mgr2@g-test.com", UserRole.manager, "manager")
    headers2 = _login_as(client, "mgr2@g-test.com")
    staged = client.post(
        f"/api/v1/admin/orders/{order_id}/cancel",
        json={"reason": "Above both managers", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert staged.json()["refund"].get("requires_approval") is True
    row_id = staged.json()["refund"]["refund_row_id"]
    # A second manager (₹5k limit) cannot rubber-stamp a ₹25k refund.
    denied = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=headers2
    )
    assert denied.status_code == 400, denied.text
    assert "authority" in denied.json()["detail"]
    # An admin (unlimited) still can.
    approved = client.post(
        f"/api/v1/admin/refunds/{row_id}/approve", headers=_admin_headers
    )
    assert approved.status_code == 200, approved.text


def test_staging_alerts_only_eligible_approvers(client):
    # Fresh above-limit staging by the manager.
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "12000.00")
        order_id = str(order.id)
    staged = client.post(
        f"/api/v1/admin/orders/{order_id}/cancel",
        json={"reason": "Needs a second pair of eyes", "refund_choice": "now"},
        headers=_manager_headers,
    )
    assert staged.json()["refund"].get("requires_approval") is True

    with _testing_session() as s:
        from app.models.notification import Notification
        rows = s.execute(
            select(Notification).where(
                Notification.type == "refund_approval"
            )
        ).scalars().all()
        assert len(rows) >= 1
        alert = rows[-1]
        # Admin (unlimited) is alerted...
        from app.models.user import User as U
        admin = s.execute(
            select(U).where(U.email == "owner@g-test.com")).scalars().one()
        assert any(r.user_id == admin.id for r in rows)
        # ...requesting manager is not (can't approve their own anyway).
        manager = s.execute(
            select(U).where(U.email == "mgr@g-test.com")).scalars().one()
        assert all(r.user_id != manager.id for r in rows)
        # Alert is staff-audience: visible in the admin bell feed.
        items, _, unread = notification_repo.list_for_user(
            s, admin.id, audience="staff")
        assert any(r.type.value == "refund_approval" for r in items)
        assert unread >= 1
        # ...and invisible on the storefront bell.
        shopper_items, _, _ = notification_repo.list_for_user(
            s, admin.id, audience="shopper")
        assert all(r.type.value != "refund_approval" for r in shopper_items)


# ---------- Forward-only status workflow ----------

def test_status_workflow_is_forward_only(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "1500.00")
        order_id = str(order.id)
    # Legal single step (fixture orders start confirmed).
    ok = client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"status": "processing"},
        headers=_admin_headers,
    )
    assert ok.status_code == 200, ok.text
    # Skipping a stage (processing -> delivered) is rejected...
    skip = client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"status": "delivered"},
        headers=_admin_headers,
    )
    assert skip.status_code == 400, skip.text
    assert "Allowed next: shipped" in skip.json()["detail"]
    # ...and moving backwards is rejected.
    back = client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"status": "pending"},
        headers=_admin_headers,
    )
    assert back.status_code == 400, back.text
    # RTO is only reachable from shipped legs, not from confirmed.
    rto = client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"status": "rto"},
        headers=_admin_headers,
    )
    assert rto.status_code == 400, rto.text


def test_provider_mismatch_returns_409_with_figures_then_reconcile_heals(client):
    from unittest.mock import patch as _patch
    from app.api.v1.admin import refunds as refunds_module

    class _FakeProvider:
        def get_charge_refund_state(self, payment_id):
            return {
                "charge_id": "ch_test",
                "charge_total": 874.82,
                "currency": "INR",
                "refunded_total": 831.08,
                "refunds": [{"id": "re_external_1", "amount": 831.08,
                             "status": "succeeded"}],
            }

    # Order whose charge was refunded OUTSIDE the app (mirrors the live case).
    # Order whose charge was refunded OUTSIDE the app (provider truth only).
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "874.82")
        from app.models.order import OrderStatus as OS
        order.status = OS.CANCELLED  # stranded money, like the legacy flips
        s.add(order)
        s.commit()
        order_id = str(order.id)
    _fake_psp.fail_next_with = (
        "Refund amount (₹831.08) is greater than unrefunded amount "
        "on charge (₹43.74)"
    )
    _fake_psp.provider_state = {
        "charge_id": "ch_test",
        "charge_total": 874.82,
        "currency": "INR",
        "refunded_total": 831.08,
        "refunds": [{"id": "re_external_1", "amount": 831.08,
                     "status": "succeeded"}],
    }
    try:
        resp = client.post(
            f"/api/v1/admin/orders/{order_id}/refund",
            json={"reason": "Return received"},
            headers=_admin_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()["detail"]
        assert body["code"] == "provider_mismatch"
        assert body["provider_refunded"] == 831.08
        assert body["provider_remaining"] == 43.74

        # Reconcile records the external refund and re-derives the total.
        with _patch.object(
            refunds_module.refund_service,
            "get_payment_service_for_payment",
            return_value=_FakeProvider(),
        ):
            synced = client.post(
                f"/api/v1/admin/orders/{order_id}/reconcile-refund",
                headers=_admin_headers,
            )
        assert synced.status_code == 200, synced.text
        assert synced.json()["synced_rows"] == 1
        assert synced.json()["recorded_refunded"] == 831.08

        # Idempotent: second run changes nothing.
        with _patch.object(
            refunds_module.refund_service,
            "get_payment_service_for_payment",
            return_value=_FakeProvider(),
        ):
            again = client.post(
                f"/api/v1/admin/orders/{order_id}/reconcile-refund",
                headers=_admin_headers,
            )
        assert again.json()["synced_rows"] == 0

        # The external ₹831.08 already baked in our 5% CONFIRMED fee
        # (874.82 − 43.74), so policy says nothing remains: the follow-up
        # attempt rejects the now-terminal fully-refunded policy balance.
        final = client.post(
            f"/api/v1/admin/orders/{order_id}/refund",
            json={"reason": "Remaining balance"},
            headers=_admin_headers,
        )
        assert final.status_code == 400, final.text
        assert "already been refunded" in final.json()["detail"]

        # ...and the order drops out of the action queue.
        queue = client.get(
            "/api/v1/admin/refunds/attention", headers=_admin_headers
        ).json()
        assert all(o["order_id"] != order_id for o in queue["orders"])
    finally:
        _fake_psp.fail_next_with = None
        _fake_psp.provider_state = None


def test_status_endpoint_rejects_money_states(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "1500.00")
        order_id = str(order.id)
    for target in ("cancelled", "refunded"):
        resp = client.put(
            f"/api/v1/admin/orders/{order_id}/status",
            json={"status": target},
            headers=_admin_headers,
        )
        assert resp.status_code == 400, resp.text
        assert "cannot be set directly" in resp.json()["detail"]
    # Ordinary transitions still work.
    ok = client.put(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"status": "processing"},
        headers=_admin_headers,
    )
    assert ok.status_code == 200, ok.text


def test_standalone_refund_on_cancelled_order(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "4000.00")
        # Simulate the legacy hole: cancelled via status flip, money intact.
        from app.models.order import OrderStatus as OS
        order.status = OS.CANCELLED
        s.add(order)
        s.commit()
        order_id = str(order.id)
    calls_before = _fake_psp.calls
    # Admin (unlimited) executes immediately.
    resp = client.post(
        f"/api/v1/admin/orders/{order_id}/refund",
        json={"reason": "Cleanup of status-only cancel"},
        headers=_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["processed"] is True
    assert _fake_psp.calls == calls_before + 1
    # Fully refunded now — second attempt is refused outright.
    again = client.post(
        f"/api/v1/admin/orders/{order_id}/refund",
        json={"reason": "Again"},
        headers=_admin_headers,
    )
    assert again.status_code == 400, again.text
    assert "already" in again.json()["detail"].lower()
    assert _fake_psp.calls == calls_before + 1


def test_duplicate_pending_request_rejected_with_409(client):
    with _testing_session() as s:
        from app.models.user import User as U
        shopper = s.get(U, UUID(_ids["shopper"]))
        addr = s.get(Address, UUID(_ids["shopper_addr"]))
        order = _make_order(s, shopper, addr, "26000.00")
        from app.models.order import OrderStatus as OS
        order.status = OS.CANCELLED
        s.add(order)
        s.commit()
        order_id = str(order.id)
    first = client.post(
        f"/api/v1/admin/orders/{order_id}/refund",
        json={"reason": "First request"},
        headers=_manager_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json().get("requires_approval") is True
    second = client.post(
        f"/api/v1/admin/orders/{order_id}/refund",
        json={"reason": "Accidental double click"},
        headers=_manager_headers,
    )
    assert second.status_code == 409, second.text
    assert "awaiting approval" in second.json()["detail"]


# ---------- Coupon hygiene (pure function) ----------

def test_internal_only_coupon_rejected_at_validation():
    coupon = Coupon(
        code="STAFF100", discount_type="percentage", value=10,
        is_active=True, internal_only=True,
        valid_from=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc),
        max_uses_per_user=1,
    )
    from decimal import Decimal as D
    valid, message = validate_coupon(coupon, D("500"), None, 0)
    assert valid is False
    assert "not valid" in message


# ---------- Least privilege: escalation blocks + audit tiering ----------

def _add_custom_role(session: Session, slug: str,
                     permission_keys: set[str]) -> Role:
    """Create a non-system role holding exactly ``permission_keys``."""
    perms = {
        p.key: p for p in session.execute(select(Permission)).scalars().all()
    }
    role = rbac_repo.get_role_by_slug(session, slug)
    if role is None:
        role = Role(name=slug.title(), slug=slug,
                    description="guardrail test")
        session.add(role)
        session.flush()
    for key in permission_keys:
        session.add(
            RolePermissionLink(role_id=role.id, permission_id=perms[key].id)
        )
    session.commit()
    session.refresh(role)
    return role


def _login_as(client, email: str) -> dict:
    """Full login (challenge + OTP) → auth headers for `email`."""
    limiter._storage.reset()
    challenge = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert challenge.status_code == 200, challenge.text
    body = challenge.json()
    assert body.get("otp_required") is True
    verify = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": body["challenge_token"],
              "otp_code": FIXED_CODE},
    )
    assert verify.status_code == 200, verify.text
    return {"Authorization": f"Bearer {verify.json()['access_token']}"}


def test_invite_cannot_mint_unheld_privileges(client):
    """An inviter may only hand out power they already hold themselves
    (grant ⊆ held across the whole permission set, not just the two
    admin-minting keys)."""
    with _testing_session() as s:
        # Can invite, but holds NEITHER users.manage_roles NOR roles.manage.
        _add_custom_role(s, "recruiter", {"users.view", "users.manage_roles"})
        _add_custom_role(s, "greeter", {"users.view"})
        _make_user(s, "recruiter@g-test.com", UserRole.staff, "recruiter")
    headers = _login_as(client, "recruiter@g-test.com")

    # In scope: `greeter` grants only users.view (held) → allowed.
    ok = client.post(
        "/api/v1/admin/invites",
        json={"email": "ok-hire@g-test.com", "role_slugs": ["greeter"]},
        headers=headers,
    )
    assert ok.status_code == 201, ok.text

    # Out of subset: `staff` grants products.view etc. (not held) → blocked.
    blocked_staff = client.post(
        "/api/v1/admin/invites",
        json={"email": "staff-hire@g-test.com", "role_slugs": ["staff"]},
        headers=headers,
    )
    assert blocked_staff.status_code == 403, blocked_staff.text
    assert "privilege escalation" in blocked_staff.json()["detail"]

    # Out of scope: `admin` grants roles.manage (not held) → blocked.
    blocked = client.post(
        "/api/v1/admin/invites",
        json={"email": "evil-hire@g-test.com", "role_slugs": ["admin"]},
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    assert "privilege escalation" in blocked.json()["detail"]

    # The blocked invite must leave no half-written row behind.
    with _testing_session() as s:
        leftover = s.execute(
            select(StaffInvite).where(
                StaffInvite.email == "evil-hire@g-test.com"
            )
        ).scalars().first()
        assert leftover is None


def test_role_assignment_cannot_grant_unheld_privileges(client):
    """Same escalation block on the role-assignment path as on invites
    (grant ⊆ held across the whole permission set)."""
    with _testing_session() as s:
        target = _make_user(
            s, "promote-me@g-test.com", UserRole.customer, "customer"
        )
        recruiter = s.execute(
            select(User).where(User.email == "recruiter@g-test.com")
        ).scalars().one()
        target_id, recruiter_id = str(target.id), str(recruiter.id)
    headers = _login_as(client, "recruiter@g-test.com")

    blocked = client.put(
        f"/api/v1/admin/users/{target_id}/roles",
        json={"role_slugs": ["admin"]},
        headers=headers,
    )
    assert blocked.status_code == 403, blocked.text
    assert "privilege escalation" in blocked.json()["detail"]

    # The seeded `staff` role grants products.view etc., which the recruiter
    # does not hold → also blocked under grant ⊆ held.
    blocked_staff = client.put(
        f"/api/v1/admin/users/{target_id}/roles",
        json={"role_slugs": ["staff"]},
        headers=headers,
    )
    assert blocked_staff.status_code == 403, blocked_staff.text

    # Nothing partial leaked into the target's role set.
    unchanged = client.get(
        f"/api/v1/admin/users/{target_id}/roles", headers=_admin_headers
    )
    assert unchanged.json() == ["customer"], unchanged.text

    # In scope: `greeter` grants only users.view (held) → allowed.
    allowed = client.put(
        f"/api/v1/admin/users/{target_id}/roles",
        json={"role_slugs": ["greeter"]},
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json() == ["greeter"]

    # No self-promotion path at all.
    self_try = client.put(
        f"/api/v1/admin/users/{recruiter_id}/roles",
        json={"role_slugs": ["recruiter"]},
        headers=headers,
    )
    assert self_try.status_code == 400, self_try.text


def test_audit_log_identity_entities_need_users_view(client):
    """reports.view alone (auditor) sees operational rows, not identity."""
    with _testing_session() as s:
        _add_custom_role(s, "auditor", {"reports.view", "orders.view"})
        _make_user(s, "auditor@g-test.com", UserRole.staff, "auditor")
    headers = _login_as(client, "auditor@g-test.com")

    # Asking for identity entities is refused, not silently emptied.
    for entity in ("user", "role", "invite"):
        denied = client.get(
            "/api/v1/admin/audit-log",
            params={"entity": entity},
            headers=headers,
        )
        assert denied.status_code == 403, denied.text

    # The unfiltered feed hides identity rows...
    listing = client.get(
        "/api/v1/admin/audit-log",
        params={"limit": 100},
        headers=headers,
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    entities = {e["entity"] for e in body["entries"]}
    assert entities.isdisjoint({"user", "role", "invite"}), entities
    # ...while still showing the operational trail (and reporting the
    # correct, filtered total — not the raw table count).
    assert entities & {"order", "refund"}, entities
    assert body["total"] == len(body["entries"]) > 0

    # An admin (users.view) sees identity entries and can filter on them.
    as_admin = client.get(
        "/api/v1/admin/audit-log",
        params={"entity": "invite"},
        headers=_admin_headers,
    )
    assert as_admin.status_code == 200, as_admin.text
    invite_rows = as_admin.json()["entries"]
    assert invite_rows and all(e["entity"] == "invite" for e in invite_rows)
    assert any(e["action"] == "invite.created" for e in invite_rows)


def test_audit_records_forwarded_client_ip(client):
    """Behind the panel's proxy the audit trail must log the real client."""
    with _testing_session() as s:
        buyer = s.execute(
            select(User).where(User.email == "buyer@g-test.com")
        ).scalars().one()
        order = _make_order(
            s, buyer, s.get(Address, UUID(_ids["shopper_addr"])), "810.00"
        )
        order_id = str(order.id)

    headers = dict(_admin_headers)
    headers["X-Forwarded-For"] = "203.0.113.9, 10.0.0.7"
    cancelled = client.post(
        f"/api/v1/admin/orders/{order_id}/cancel",
        json={"reason": "customer changed mind", "refund_choice": "later"},
        headers=headers,
    )
    assert cancelled.status_code == 200, cancelled.text

    from app.models.admin_audit import AdminAuditLog

    with _testing_session() as s:
        entry = s.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "order.cancelled",
                AdminAuditLog.entity_id == order_id,
            )
        ).scalars().first()
        assert entry is not None
        # Leftmost hop = the admin's browser, not the ingress address.
        assert entry.ip_address == "203.0.113.9"
