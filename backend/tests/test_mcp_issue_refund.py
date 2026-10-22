# tests/test_mcp_issue_refund.py
"""MCP two-step refund (isolated sqlite DB, stubbed payment provider).

Preview recomputes the live refundable balance and stages nothing;
execution re-resolves the caller, re-checks orders.refund, validates the
signed preview, and runs request_admin_refund (limits, approval staging,
ledger idempotency, PSP handling). No real money moves: the PSP router is
stubbed in every test that could reach it.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from app.core.config import settings

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from app.api.deps import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.admin_audit import AdminAuditLog  # noqa: E402
from app.models.order import Order, OrderStatus  # noqa: E402
from app.models.payment import Payment, PaymentProvider, PaymentStatus  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.refund import Refund, RefundStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.orders as mcp_orders  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_issue_refund_test.db"
PASSWORD = "TestPass123"


class StubPSP:
    """Scripted provider double; create_refund returns the queued result."""

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def create_refund(self, payment_id, amount=None, notes=None):
        self.calls += 1
        return dict(self.result)


def _seed_rbac(session: Session) -> None:
    for key, label, module, description in PERMISSIONS:
        session.add(Permission(key=key, label=label, module=module, description=description))
    session.flush()
    perms = {p.key: p for p in session.exec(select(Permission)).all()}
    for slug, spec in SYSTEM_ROLES.items():
        role = Role(name=spec["name"], slug=slug, description=spec["description"],
                    is_system=True, max_refund_amount=spec["max_refund_amount"])
        session.add(role)
        session.flush()
        for key in spec["permissions"]:
            session.add(RolePermissionLink(role_id=role.id, permission_id=perms[key].id))
    session.commit()


def _make_user(session: Session, email: str, legacy: UserRole) -> User:
    user = User(
        email=email, username=f"u_{uuid4().hex[:8]}",
        password_hash=hash_password(PASSWORD), role=legacy,
        full_name=email, is_active=True, email_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    role = rbac_repo.get_role_by_slug(session, legacy.value)
    rbac_repo.set_user_roles(session, user, [role])
    session.refresh(user)
    return user


def _make_paid_order(session: Session, owner: User, number: str, status, total: str) -> Order:
    order = Order(
        order_number=number, user_id=owner.id,
        shipping_address_id=uuid4(), billing_address_id=uuid4(),
        subtotal=Decimal(total), grand_total=Decimal(total),
        status=status, payment_method="online", payment_status="paid",
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    session.add(Payment(
        order_id=order.id, provider=PaymentProvider.RAZORPAY,
        provider_payment_id=f"order_rzp_{number}",
        provider_payment_intent=f"pay_rzp_{number}",
        amount=Decimal(total), currency="INR", status=PaymentStatus.SUCCEEDED,
    ))
    session.commit()
    return order


@pytest.fixture(scope="module")
def env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)

    originals = (mcp_auth.engine, mcp_guards.engine, mcp_orders.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_orders.engine = test_engine

    with TestingSession() as s:
        _seed_rbac(s)
        manager = _make_user(s, "manager@mcp-refund.com", UserRole.manager)
        admin = _make_user(s, "admin@mcp-refund.com", UserRole.admin)
        staff = _make_user(s, "staff@mcp-refund.com", UserRole.staff)
        customer = _make_user(s, "shopper@mcp-refund.com", UserRole.customer)
        cancelled = _make_paid_order(s, customer, "ORD-RFD-001", OrderStatus.CANCELLED, "1000.00")
        pending = _make_paid_order(s, customer, "ORD-RFD-002", OrderStatus.PENDING, "500.00")
        big = _make_paid_order(s, customer, "ORD-RFD-003", OrderStatus.CANCELLED, "20000.00")
        cod = Order(
            order_number="ORD-RFD-004", user_id=customer.id,
            shipping_address_id=uuid4(), billing_address_id=uuid4(),
            subtotal=Decimal("200.00"), grand_total=Decimal("200.00"),
            status=OrderStatus.PENDING, payment_method="cod", payment_status="pending",
        )
        s.add(cod)
        s.commit()
        ids = {o.order_number: str(o.id) for o in (cancelled, pending, big, cod)}

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email, role=user.role.value, audience=audience,
            token_version=user.token_version,
        )

    def override_session():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    limiter._storage.reset()
    try:
        with TestClient(app) as client:
            yield {
                "client": client, "Session": TestingSession,
                "manager": token_for(manager), "admin": token_for(admin),
                "staff": token_for(staff), "customer": token_for(customer),
                "storefront": token_for(manager, audience="storefront"),
                "ids": ids,
            }
    finally:
        app.dependency_overrides.clear()
        mcp_auth.engine, mcp_guards.engine, mcp_orders.engine = originals


def run(coro):
    return asyncio.run(coro)


def preview(env, number, **kwargs):
    return run(mcp_orders.issue_refund(order_id=number, token=env["manager"], **kwargs))


# 1. preview recomputes the live balance, stages nothing
def test_preview_full_balance(env):
    res = preview(env, "ORD-RFD-001")
    assert res["success"] is True and res["requires_confirmation"] is True
    assert Decimal(res["amount"]) == Decimal(res["remaining_before"]) > 0
    assert Decimal(res["amount"]) < Decimal("1000.00")  # restocking fee retained
    assert res["requires_approval"] is False
    assert isinstance(res["preview_token"], str)
    with env["Session"]() as s:
        assert s.exec(select(Refund)).all() == []  # no ledger row at preview


def test_preview_partial_amount(env):
    res = preview(env, "ORD-RFD-001", amount="100.00")
    assert res["success"] is True and res["amount"] == "100.00"


def test_preview_over_balance_rejected(env):
    res = preview(env, "ORD-RFD-001", amount="99999.00")
    assert res["success"] is False and "exceeds refundable balance" in res["error"]


def test_preview_bad_amount(env):
    for bad in ("abc", "-5", "0"):
        res = preview(env, "ORD-RFD-001", amount=bad)
        assert res["success"] is False, bad


def test_preview_cod_no_money(env):
    res = preview(env, "ORD-RFD-004")
    assert res["success"] is False and "no captured online payment" in res["error"]


def test_preview_unknown_order(env):
    assert preview(env, "ORD-NOPE")["error"].startswith("Order ORD-NOPE not found")


# 2. auth matrix
def test_preview_customer_forbidden(env):
    res = run(mcp_orders.issue_refund(order_id="ORD-RFD-001", token=env["customer"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


def test_preview_staff_no_refund_perm(env):
    res = run(mcp_orders.issue_refund(order_id="ORD-RFD-001", token=env["staff"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


def test_preview_invalid_jwt(env):
    assert run(mcp_orders.issue_refund(order_id="ORD-RFD-001", token="bad"))["success"] is False


def test_preview_storefront_forbidden(env):
    res = run(mcp_orders.issue_refund(order_id="ORD-RFD-001", token=env["storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


# 3. execute within authority: single PSP call, ledger + order updated
def test_execute_success(env):
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_mcp_001"})
    with stub_psp_stub(stub):
        pre = preview(env, "ORD-RFD-002", amount="100.00")
        assert pre["success"] is True and pre["requires_approval"] is False
        res = run(mcp_orders.issue_refund(
            order_id="ORD-RFD-002", preview_token=pre["preview_token"],
            confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["processed"] is True
    assert res["refund_id"] == "rfnd_mcp_001" and res["duplicate"] is False
    assert stub.calls == 1
    with env["Session"]() as s:
        rows = s.exec(select(Refund).where(Refund.order_id == _oid(env, "ORD-RFD-002"))).all()
        assert len(rows) == 1 and rows[0].status == RefundStatus.EXECUTED
        assert rows[0].provider_refund_id == "rfnd_mcp_001"


def stub_psp_stub(stub):
    return mock.patch(
        "app.services.refund_service.get_payment_service_for_payment", return_value=stub)


def _oid(env, number):
    from uuid import UUID as _UUID

    return _UUID(env["ids"][number])


# 4. replay / concurrent retry: same token executes once at the provider
def test_execute_replay_single_psp_call(env):
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_mcp_replay"})
    with stub_psp_stub(stub):
        pre = preview(env, "ORD-RFD-001", amount="100.00")
        assert pre["success"] is True
        args = dict(order_id="ORD-RFD-001", preview_token=pre["preview_token"],
                    confirmed=True, token=env["manager"])
        first = run(mcp_orders.issue_refund(**args))
        second = run(mcp_orders.issue_refund(**args))
    assert first["success"] is True and first["processed"] is True
    assert second["success"] is True and second["duplicate"] is True
    assert stub.calls == 1, "provider must see exactly one refund request"


# 5. above-limit staging: no PSP call, approval row, honest flags
def test_execute_above_limit_stages_approval(env):
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_should_not_happen"})
    with stub_psp_stub(stub):
        pre = preview(env, "ORD-RFD-003")
        assert pre["success"] is True and pre["requires_approval"] is True
        res = run(mcp_orders.issue_refund(
            order_id="ORD-RFD-003", preview_token=pre["preview_token"],
            confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["approval_staged"] is True
    assert res["processed"] is False
    assert stub.calls == 0
    with env["Session"]() as s:
        row = s.exec(select(Refund).where(Refund.order_id == _oid(env, "ORD-RFD-003"))).first()
        assert row is not None and row.status == RefundStatus.PENDING_APPROVAL


# 6. forged / expired / cross-user / stale previews rejected
def test_preview_token_binding(env):
    pre = preview(env, "ORD-RFD-002")
    tok = pre["preview_token"]
    base = dict(order_id="ORD-RFD-002", preview_token=tok, confirmed=True, token=env["manager"])
    forged = jwt.encode({"sub": "x", "type": "mcp_refund_preview",
                         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                        "wrong-secret", algorithm="HS256")
    assert "preview" in run(mcp_orders.issue_refund(
        **{**base, "preview_token": forged}))["error"].lower()
    expired = jwt.encode({"sub": "x", "type": "mcp_refund_preview",
                          "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
                         settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    assert "preview" in run(mcp_orders.issue_refund(
        **{**base, "preview_token": expired}))["error"].lower()
    # different user, same token
    other = run(mcp_orders.issue_refund(**{**base, "token": env["admin"]}))
    assert other["success"] is False
    # missing token
    assert "preview_token" in run(mcp_orders.issue_refund(
        order_id="ORD-RFD-002", confirmed=True, token=env["manager"]))["error"]


def test_stale_amount_rejected(env):
    # Same deterministic key as the earlier ORD-RFD-002 refund: replaying
    # is an idempotent duplicate, not a second provider call.
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_mcp_stale"})
    with stub_psp_stub(stub):
        pre = preview(env, "ORD-RFD-002", amount="50.00")
        args = dict(order_id="ORD-RFD-002", preview_token=pre["preview_token"],
                    confirmed=True, token=env["manager"])
        first = run(mcp_orders.issue_refund(**args))
        assert first["success"] is True and first["duplicate"] is True
        assert stub.calls == 0
    # Drain the balance below the token amount, then replay -> stale.
    with env["Session"]() as s:
        from uuid import UUID as _UUID
        order = s.exec(select(Order).where(Order.id == _UUID(env["ids"]["ORD-RFD-002"]))).first()
        order.refund_amount = order.grand_total
        s.add(order)
        s.commit()
    drained = run(mcp_orders.issue_refund(**args))
    assert drained["success"] is False and "stale" in drained["error"].lower()


# 7. provider failure is honest: FAILED row, success False, no success claim
def test_provider_failure_honest(env):
    stub = StubPSP({"status": "failed", "error": "card declined"})
    with stub_psp_stub(stub):
        pre = run(mcp_orders.issue_refund(
            order_id="ORD-RFD-003", amount="100.00", token=env["admin"]))
        assert pre["success"] is True and pre["requires_approval"] is False
        res = run(mcp_orders.issue_refund(
            order_id="ORD-RFD-003", preview_token=pre["preview_token"],
            confirmed=True, token=env["admin"]))  # unlimited authority
    assert res["success"] is False and "card declined" in res["error"]
    with env["Session"]() as s:
        rows = s.exec(select(Refund).where(Refund.order_id == _oid(env, "ORD-RFD-003"))).all()
        assert any(r.status == RefundStatus.FAILED for r in rows)


# 8. endpoint + registration + neighbors
def test_endpoint_refund(env):
    client = env["client"]
    assert client.post("/api/v1/mcp/refund",
                       json={"order_id": "x", "preview_token": "y"}).status_code in (401, 403)
    denied = client.post("/api/v1/mcp/refund",
                         json={"order_id": "x", "preview_token": "y"},
                         headers={"Authorization": f"Bearer {env['customer']}"})
    assert denied.status_code == 400
    pre = preview(env, "ORD-RFD-001", amount="10.00")
    assert pre["success"] is True
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_mcp_endpoint"})
    with stub_psp_stub(stub):
        ok = client.post(
            "/api/v1/mcp/refund",
            json={"order_id": "ORD-RFD-001", "amount": "10.00",
                  "reason": pre.get("reason", ""), "preview_token": pre["preview_token"]},
            headers={"Authorization": f"Bearer {env['manager']}"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["processed"] is True


def test_registered_tools():
    names = {t.name for t in run(mcp.list_tools())}
    assert {"whoami", "check_orders_view", "get_order", "list_orders",
            "cancel_order", "issue_refund"} <= names


def test_get_order_still_works(env):
    res = run(mcp_orders.get_order("ORD-RFD-001", token=env["manager"]))
    assert res["success"] is True


def test_preview_breakdown_matches_service(env):
    # Breakdown identity holds generally: amount equals calculate_refund()'s
    # net figure (which already deducts fees and prior refunds), and the
    # preview states no further fee is deducted at execution.
    from app.services import refund_service as refund_svc

    res = preview(env, "ORD-RFD-001")
    assert res["success"] is True
    with env["Session"]() as s:
        order = s.exec(select(Order).where(Order.order_number == "ORD-RFD-001")).first()
        basis = refund_svc.status_at_cancellation(s, order)
        expected = refund_svc.calculate_refund(order, basis)
    assert Decimal(res["order_total"]) == order.grand_total
    assert Decimal(res["restocking_fee"]) == expected["restocking_fee"]
    assert Decimal(res["refund_to_customer"]) == expected["refund_amount"]
    assert Decimal(res["amount"]) == expected["refund_amount"]
    assert res["additional_fee_at_execution"] == "0.00"
    # The fee is retained inside the net figure, never subtracted twice:
    assert Decimal(res["order_total"]) - Decimal(res["restocking_fee"]) - expected["already_refunded"] == Decimal(
        res["refund_to_customer"]
    )
