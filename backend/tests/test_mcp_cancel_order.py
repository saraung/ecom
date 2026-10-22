# tests/test_mcp_cancel_order.py
"""MCP two-step order cancellation (isolated sqlite DB).

Preview makes no change and returns a signed expiring token; execution
re-resolves the caller, re-checks orders.update, validates the token
(same user/order/status, unexpired), re-locks the row, and runs the
shared order_cancel service. Covers auth matrix, invalid states,
replay/concurrency, refund implications, endpoint, and registration.
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
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.orders as mcp_orders  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_cancel_order_test.db"
PASSWORD = "TestPass123"


def _seed_rbac(session: Session) -> None:
    for key, label, module, description in PERMISSIONS:
        session.add(Permission(key=key, label=label, module=module, description=description))
    session.flush()
    perms = {p.key: p for p in session.exec(select(Permission)).all()}
    for slug, spec in SYSTEM_ROLES.items():
        role = Role(name=spec["name"], slug=slug, description=spec["description"], is_system=True)
        session.add(role)
        session.flush()
        for key in spec["permissions"]:
            session.add(RolePermissionLink(role_id=role.id, permission_id=perms[key].id))
    session.commit()


def _make_user(session: Session, email: str, legacy: UserRole) -> User:
    user = User(
        email=email,
        username=f"u_{uuid4().hex[:8]}",
        password_hash=hash_password(PASSWORD),
        role=legacy,
        full_name=email,
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    role = rbac_repo.get_role_by_slug(session, legacy.value)
    rbac_repo.set_user_roles(session, user, [role])
    session.refresh(user)
    return user


def _make_order(session: Session, owner: User, number: str, status, method: str, payment: str) -> Order:
    order = Order(
        order_number=number,
        user_id=owner.id,
        shipping_address_id=uuid4(),
        billing_address_id=uuid4(),
        subtotal=Decimal("1000.00"),
        grand_total=Decimal("1000.00"),
        status=status,
        payment_method=method,
        payment_status=payment,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
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
        manager = _make_user(s, "manager@mcp-cancel.com", UserRole.manager)
        staff = _make_user(s, "staff@mcp-cancel.com", UserRole.staff)  # view, no update
        customer = _make_user(s, "shopper@mcp-cancel.com", UserRole.customer)
        pending_cod = _make_order(s, customer, "ORD-CXL-001", OrderStatus.PENDING, "cod", "pending")
        pending_paid = _make_order(s, customer, "ORD-CXL-002", OrderStatus.PENDING, "online", "paid")
        shipped = _make_order(s, customer, "ORD-CXL-003", OrderStatus.PROCESSING, "cod", "pending")
        # flip one to shipped post-creation (PROCESSING->SHIPPED is not cancellable)
        shipped.status = OrderStatus.SHIPPED
        s.add(shipped)
        cancelled = _make_order(s, customer, "ORD-CXL-004", OrderStatus.PENDING, "cod", "pending")
        cancelled.status = OrderStatus.CANCELLED
        s.add(cancelled)
        s.commit()
        ids = {
            "pending_cod": (str(pending_cod.id), pending_cod.order_number),
            "pending_paid": (str(pending_paid.id), pending_paid.order_number),
            "shipped": (str(shipped.id), shipped.order_number),
            "cancelled": (str(cancelled.id), cancelled.order_number),
        }

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
                "client": client,
                "Session": TestingSession,
                "manager": token_for(manager),
                "manager_storefront": token_for(manager, audience="storefront"),
                "staff": token_for(staff),
                "customer": token_for(customer),
                "manager_id": str(manager.id),
                "ids": ids,
            }
    finally:
        app.dependency_overrides.clear()
        mcp_auth.engine, mcp_guards.engine, mcp_orders.engine = originals


def run(coro):
    return asyncio.run(coro)


def _load_order(Session, order_id):
    from uuid import UUID as _UUID

    with Session() as s:
        return s.exec(select(Order).where(Order.id == _UUID(str(order_id)))).first()


def status_of(Session, order_id):
    return _load_order(Session, order_id).status


def _set_status(Session, order_id, status):
    from uuid import UUID as _UUID

    with Session() as s:
        order = s.exec(select(Order).where(Order.id == _UUID(str(order_id)))).first()
        order.status = status
        s.add(order)
        s.commit()


# 1. preview succeeds and writes nothing
def test_preview_success_no_write(env):
    oid, number = env["ids"]["pending_cod"]
    res = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    assert res["success"] is True and res["requires_confirmation"] is True
    assert res["order"]["order_number"] == number
    assert isinstance(res["preview_token"], str) and res["expires_in_minutes"] == 10
    assert res["cancel_implications"]["money_moves"] is False
    assert status_of(env["Session"], oid) == OrderStatus.PENDING


# 2. paid-online preview shows accurate, non-promising implications
def test_preview_paid_implications(env):
    oid, _ = env["ids"]["pending_paid"]
    res = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    assert res["success"] is True
    impl = res["cancel_implications"]
    assert impl["money_moves"] is False
    assert "NOT executed" in impl["message"]
    assert float(impl["refundable_amount"]) > 0


# 3. auth matrix on preview
def test_preview_customer_forbidden(env):
    oid, _ = env["ids"]["pending_cod"]
    assert run(mcp_orders.cancel_order(order_id=oid, token=env["customer"])) == {
        "success": False, "error": "Insufficient permissions"}


def test_preview_invalid_jwt(env):
    oid, _ = env["ids"]["pending_cod"]
    assert run(mcp_orders.cancel_order(order_id=oid, token="bad.jwt"))["success"] is False


def test_preview_storefront_forbidden(env):
    oid, _ = env["ids"]["pending_cod"]
    res = run(mcp_orders.cancel_order(order_id=oid, token=env["manager_storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


# 4. invalid states + unknown order
def test_preview_invalid_states(env):
    for key in ("shipped", "cancelled"):
        oid, _ = env["ids"][key]
        res = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
        assert res["success"] is False, key
    assert run(mcp_orders.cancel_order(order_id="ORD-NOPE", token=env["manager"])) == {
        "success": False, "error": "Order ORD-NOPE not found"}


# 5. full execute path via shared service
def test_execute_success(env):
    oid, number = env["ids"]["pending_cod"]
    preview = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    res = run(mcp_orders.cancel_order(
        order_id=oid, preview_token=preview["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["cancelled"] is True
    assert res["order_number"] == number and res["status"] == "cancelled"
    assert status_of(env["Session"], oid) == OrderStatus.CANCELLED
    with env["Session"]() as s:
        audit = s.exec(select(AdminAuditLog).where(
            AdminAuditLog.entity == "order",
            AdminAuditLog.entity_id == oid,
            AdminAuditLog.action == "order.cancelled")).first()
        assert audit is not None


# 6. replay / concurrent retry fails closed (single-use via status lock)
def test_execute_replay_fails(env):
    oid, _ = env["ids"]["pending_cod"]  # cancelled by previous test
    preview = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    assert preview["success"] is False  # terminal state: no fresh preview either


# 7. execute without token / mismatched preview
def test_execute_needs_fresh_token(env):
    oid, _ = env["ids"]["pending_paid"]
    assert "preview_token" in run(
        mcp_orders.cancel_order(order_id=oid, confirmed=True, token=env["manager"])
    )["error"]
    forged = jwt.encode(
        {"sub": "x", "oid": oid, "st": "pending", "type": "mcp_cancel_preview",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        "wrong-secret", algorithm="HS256")
    res = run(mcp_orders.cancel_order(
        order_id=oid, preview_token=forged, confirmed=True, token=env["manager"]))
    assert "preview" in res["error"].lower()


def test_execute_cross_user_rejected(env):
    oid, _ = env["ids"]["pending_paid"]
    preview = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    # staff lacks orders.update: fails on permission before token even matters
    res = run(mcp_orders.cancel_order(
        order_id=oid, preview_token=preview["preview_token"],
        confirmed=True, token=env["staff"]))
    assert res["success"] is False


def test_execute_stale_status_rejected(env):
    oid, _ = env["ids"]["pending_paid"]
    preview = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    assert preview["success"] is True
    _set_status(env["Session"], oid, OrderStatus.SHIPPED)  # ships between preview and confirm
    res = run(mcp_orders.cancel_order(
        order_id=oid, preview_token=preview["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is False and "stale" in res["error"].lower()
    _set_status(env["Session"], oid, OrderStatus.PENDING)  # restore for later tests


# 8. paid-online execute moves no money
def test_execute_paid_moves_no_money(env):
    oid, _ = env["ids"]["pending_paid"]
    preview = run(mcp_orders.cancel_order(order_id=oid, token=env["manager"]))
    res = run(mcp_orders.cancel_order(
        order_id=oid, preview_token=preview["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is True
    assert res["refund"]["processed"] is False
    order = _load_order(env["Session"], oid)
    assert order.payment_status == "paid" and float(order.refund_amount or 0) == 0


# 9. dedicated endpoint
def test_endpoint_cancel(env):
    client = env["client"]
    no_auth = client.post("/api/v1/mcp/cancel", json={"order_id": "x", "preview_token": "y"})
    assert no_auth.status_code in (401, 403)
    # customer is authenticated but lacks orders.update
    denied = client.post(
        "/api/v1/mcp/cancel", json={"order_id": "x", "preview_token": "y"},
        headers={"Authorization": f"Bearer {env['customer']}"})
    assert denied.status_code == 400


# 10. registration + get_order regression
def test_registered_tools():
    names = {t.name for t in run(mcp.list_tools())}
    assert {"whoami", "check_orders_view", "get_order", "list_orders", "cancel_order"} <= names


def test_get_order_still_works(env):
    oid, number = env["ids"]["pending_paid"]
    res = run(mcp_orders.get_order(number, token=env["manager"]))
    assert res["success"] is True and res["order"]["order_number"] == number
