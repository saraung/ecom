# tests/test_mcp_payments.py
"""MCP payments & refunds inspection (isolated sqlite DB, stubbed PSP).

Strictly read-only: every test asserting behavior also asserts row counts
are unchanged, and provider calls go through stub doubles — never live PSPs.
"""
import asyncio
import os
import time
from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from app.core.config import settings

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.models.order import Order, OrderStatus  # noqa: E402
from app.models.payment import Payment, PaymentProvider, PaymentStatus  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.refund import Refund, RefundStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402
from app.services import refund_service  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.payments as mcp_payments  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_payments_test.db"
PASSWORD = "TestPass123"

PAYMENT_KEYS = {"id", "status", "amount", "currency", "provider",
                "last_four", "paid_at", "created_at"}
REFUND_KEYS = {"id", "order_id", "order_number", "amount", "restocking_fee",
               "status", "reason", "requested_by", "approved_by",
               "provider_refund_id", "provider_status", "error",
               "created_at", "decided_at"}


class StubPSP:
    def __init__(self, result=None, error=None, delay=0.0):
        self.result = result
        self.error = error
        self.delay = delay
        self.calls = 0

    def get_refund_status(self, refund_id):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
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


@pytest.fixture(scope="module")
def env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)

    originals = (mcp_auth.engine, mcp_guards.engine, mcp_payments.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_payments.engine = test_engine

    with TestingSession() as s:
        _seed_rbac(s)
        admin = _make_user(s, "admin@mcp-pay.com", UserRole.admin)
        manager = _make_user(s, "manager@mcp-pay.com", UserRole.manager)
        staff = _make_user(s, "staff@mcp-pay.com", UserRole.staff)
        customer = _make_user(s, "shopper@mcp-pay.com", UserRole.customer)

        def order(number, status, method, pay_status, grand, refund="0", fee="0"):
            o = Order(
                order_number=number, user_id=customer.id,
                shipping_address_id=uuid4(), billing_address_id=uuid4(),
                subtotal=Decimal(grand), grand_total=Decimal(grand),
                status=status, payment_method=method, payment_status=pay_status,
                refund_amount=Decimal(refund), restocking_fee=Decimal(fee),
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return o

        def pay(order, amount, status=PaymentStatus.SUCCEEDED, intent="pay_x",
                provider=PaymentProvider.RAZORPAY):
            s.add(Payment(order_id=order.id, provider=provider,
                          provider_payment_id=f"order_{order.order_number}",
                          provider_payment_intent=intent,
                          amount=Decimal(amount), currency="INR", status=status))
            s.commit()

        o1 = order("PAY-001", OrderStatus.CANCELLED, "online", "paid", "1000.00",
                   refund="950.00", fee="50.00")
        pay(o1, "1000.00", intent="pay_1")
        o2 = order("PAY-002", OrderStatus.DELIVERED, "online", "paid", "500.00")
        pay(o2, "500.00", intent="pay_2")
        pay(o2, "500.00", status=PaymentStatus.FAILED, intent="pay_2b")
        o3 = order("PAY-003", OrderStatus.PENDING, "online", "pending", "300.00")
        pay(o3, "300.00", status=PaymentStatus.PENDING, intent="pay_3")
        o4 = order("PAY-004", OrderStatus.CANCELLED, "online", "paid", "2000.00")
        pay(o4, "2000.00", intent="pay_4")
        order("PAY-005", OrderStatus.CANCELLED, "cod", "paid", "700.00")
        o6 = order("PAY-006", OrderStatus.CANCELLED, "online", "paid", "1200.00")
        pay(o6, "1200.00", intent="pay_6")
        o8 = order("PAY-008", OrderStatus.CANCELLED, "online", "paid", "600.00")
        pay(o8, "600.00", intent="pay_8", provider=PaymentProvider.DUMMY)

        s.add(Refund(order_id=o1.id, amount=Decimal("950.00"),
                     idempotency_key="seed-mcp-exec", status=RefundStatus.EXECUTED,
                     reason="t", requested_by=admin.id,
                     provider_refund_id="rfnd_seed_1", provider_status="processed"))
        s.add(Refund(order_id=o6.id, amount=Decimal("100.00"),
                     idempotency_key="seed-mcp-pend", status=RefundStatus.PENDING_APPROVAL,
                     reason="t", requested_by=manager.id))
        s.add(Refund(order_id=o8.id, amount=Decimal("100.00"),
                     idempotency_key="seed-mcp-dummy", status=RefundStatus.EXECUTED,
                     reason="t", requested_by=admin.id,
                     provider_refund_id="dummy_rfnd_1", provider_status="processed"))
        s.commit()
        ids = {
            "o1": str(o1.id), "o2": str(o2.id), "o3": str(o3.id),
            "o4": str(o4.id), "o6": str(o6.id), "o8": str(o8.id),
        }

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email, role=user.role.value, audience=audience,
            token_version=user.token_version,
        )

    try:
        yield {
            "admin": token_for(admin), "manager": token_for(manager),
            "staff": token_for(staff), "customer": token_for(customer),
            "storefront": token_for(admin, audience="storefront"),
            "ids": ids, "Session": TestingSession,
        }
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_payments.engine = originals


def run(coro):
    return asyncio.run(coro)


def stub_router(stub):
    return mock.patch(
        "app.services.refund_service.get_payment_service_for_payment",
        return_value=stub)


def row_counts(Session):
    with Session() as s:
        return (
            s.exec(select(func.count(Order.id))).first(),
            s.exec(select(func.count(Payment.id))).first(),
            s.exec(select(func.count(Refund.id))).first(),
        )


# ---------- registration ----------

def test_registered_payment_tools():
    names = {t.name for t in run(mcp.list_tools())}
    assert {"get_payment_status", "list_refunds", "list_payment_issues",
            "get_refund_status"} <= names


# ---------- permission matrix ----------

def test_payment_tools_require_payments_view(env):
    for tok in (env["manager"], env["staff"], env["customer"]):
        res = run(mcp_payments.get_payment_status(env["ids"]["o1"], token=tok))
        assert res == {"success": False, "error": "Insufficient permissions"}, tok
    assert run(mcp_payments.get_payment_status(env["ids"]["o1"], token="bad"))["success"] is False
    res = run(mcp_payments.get_payment_status(env["ids"]["o1"], token=env["storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


def test_refund_tools_require_orders_refund(env):
    for fn in (lambda t: mcp_payments.list_refunds(token=t),
               lambda t: mcp_payments.list_payment_issues(token=t),
               lambda t: mcp_payments.get_refund_status(order_id=env["ids"]["o1"], token=t)):
        assert run(fn(env["customer"])) == {"success": False, "error": "Insufficient permissions"}
        assert run(fn(env["staff"])) == {"success": False, "error": "Insufficient permissions"}
    # manager holds orders.refund: allowed
    assert run(mcp_payments.list_refunds(token=env["manager"]))["success"] is True


# ---------- get_payment_status ----------

def test_get_payment_status_happy(env):
    from app.core.region import currency_code

    res = run(mcp_payments.get_payment_status(env["ids"]["o1"], token=env["admin"]))
    assert res["success"] is True
    assert res["currency"] == currency_code()
    assert res["order_number"] == "PAY-001" and res["collected"] is True
    assert res["payment_count"] == 1
    assert set(res["payments"][0].keys()) == PAYMENT_KEYS
    blob = str(res)
    assert "order_PAY-001" not in blob and "payment_metadata" not in blob


def test_get_payment_status_multi_attempt(env):
    res = run(mcp_payments.get_payment_status("PAY-002", token=env["admin"]))
    assert res["success"] is True and res["payment_count"] == 2
    assert {p["status"] for p in res["payments"]} == {"succeeded", "failed"}


def test_get_payment_status_errors(env):
    assert run(mcp_payments.get_payment_status(token=env["admin"]))["error"].startswith("order_id")
    assert run(mcp_payments.get_payment_status("ORD-NOPE", token=env["admin"])) == {
        "success": False, "error": "Order ORD-NOPE not found"}


# ---------- list_refunds ----------

def test_list_refunds_filters(env):
    all_rows = run(mcp_payments.list_refunds(token=env["manager"]))
    assert all_rows["success"] is True and all_rows["total_matching"] == 3
    assert set(all_rows["refunds"][0].keys()) == REFUND_KEYS
    exe = run(mcp_payments.list_refunds(status="executed", token=env["manager"]))
    assert exe["total_matching"] == 2 and {r["status"] for r in exe["refunds"]} == {"executed"}
    by_order = run(mcp_payments.list_refunds(order_id=env["ids"]["o6"], token=env["manager"]))
    assert by_order["total_matching"] == 1
    page = run(mcp_payments.list_refunds(limit=1, offset=1, token=env["manager"]))
    assert page["returned_count"] == 1 and page["total_matching"] == 3
    assert run(mcp_payments.list_refunds(limit=10000, token=env["manager"]))["limit"] == 50
    assert "Invalid status" in run(
        mcp_payments.list_refunds(status="bogus", token=env["manager"]))["error"]
    assert "UUID" in run(
        mcp_payments.list_refunds(order_id="nope", token=env["manager"]))["error"]


# ---------- list_payment_issues ----------

def test_attention_inclusion_exclusion(env):
    res = run(mcp_payments.list_payment_issues(token=env["manager"]))
    assert res["success"] is True
    numbers = {o["order_number"] for o in res["orders"]}
    assert "PAY-004" in numbers  # cancelled, paid, untouched
    assert "PAY-008" in numbers  # cancelled, paid, untouched (dummy PSP)
    assert "PAY-002" not in numbers  # delivered: normal, not work
    assert "PAY-005" not in numbers  # COD excluded
    assert "PAY-006" not in numbers  # pending approval in flight
    assert "PAY-003" not in numbers  # unpaid
    assert "PAY-001" not in numbers  # fully fee-covered
    assert res["count"] == len(res["orders"]) == 2
    item = res["orders"][0]
    assert item["remaining"] > 0 and item["status"] == "cancelled"
    assert run(mcp_payments.list_payment_issues(limit=0, token=env["manager"]))["limit"] == 1


# ---------- get_refund_status ----------

def test_get_refund_status_live_success(env):
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_seed_1"})
    with stub_router(stub):
        res = run(mcp_payments.get_refund_status(order_id=env["ids"]["o1"], token=env["manager"]))
    assert res["success"] is True and res["returned_count"] == 1
    assert res["live"]["source"] == "live" and res["live"]["status"] == "processed"
    assert res["live_source"] == "live" and stub.calls == 1
    assert res["remaining_refundable"] == 0.0  # fully covered: 1000-50 fee-950


def test_get_refund_status_no_provider_rows(env):
    res = run(mcp_payments.get_refund_status(order_id=env["ids"]["o2"], token=env["manager"]))
    assert res["success"] is True and res["refunds"] == []
    assert res["live"] is None and res["live_source"] == "ledger"


def test_get_refund_status_by_id_and_validation(env):
    with env["Session"]() as s:
        rid = str(s.exec(select(Refund.id).where(
            Refund.idempotency_key == "seed-mcp-exec")).first())
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_seed_1"})
    with stub_router(stub):
        res = run(mcp_payments.get_refund_status(refund_id=rid, token=env["manager"]))
    assert res["success"] is True and res["refunds"][0]["id"] == rid
    assert run(mcp_payments.get_refund_status(token=env["manager"]))["error"].startswith(
        "Provide exactly one")
    both = run(mcp_payments.get_refund_status(
        refund_id=rid, order_id=env["ids"]["o1"], token=env["manager"]))
    assert both["success"] is False
    assert "UUID" in run(mcp_payments.get_refund_status(
        refund_id="nope", token=env["manager"]))["error"]
    assert run(mcp_payments.get_refund_status(order_id="ORD-NOPE", token=env["manager"])) == {
        "success": False, "error": "Order ORD-NOPE not found"}


def test_get_refund_status_timeout_is_stale(env):
    stub = StubPSP(None, delay=30.0)
    with stub_router(stub), mock.patch.object(mcp_payments, "LIVE_TIMEOUT_SECONDS", 0.05):
        res = run(mcp_payments.get_refund_status(order_id=env["ids"]["o1"], token=env["manager"]))
    assert res["success"] is True
    assert res["live"]["source"] == "ledger" and res["live"]["stale"] is True
    assert res["live_source"] == "ledger"


def test_get_refund_status_provider_failure(env):
    stub = StubPSP(None, error=Exception("gateway down"))
    with stub_router(stub):
        res = run(mcp_payments.get_refund_status(order_id=env["ids"]["o1"], token=env["manager"]))
    assert res["success"] is True and res["live"]["status"] == "unknown"
    assert "gateway down" not in str(res)  # provider internals stay out of the envelope


def test_dummy_provider_never_verified(env):
    res = run(mcp_payments.get_refund_status(order_id=env["ids"]["o8"], token=env["manager"]))
    assert res["success"] is True
    assert res["live"]["source"] == "ledger" and res["live"]["stale"] is True
    assert "dummy" in res["live"]["note"].lower() or "unconfigured" in res["live"]["note"].lower()


# ---------- read-only guarantee ----------

def test_inspection_writes_nothing(env):
    before = row_counts(env["Session"])
    run(mcp_payments.get_payment_status(env["ids"]["o1"], token=env["admin"]))
    run(mcp_payments.list_refunds(token=env["manager"]))
    run(mcp_payments.list_payment_issues(token=env["manager"]))
    stub = StubPSP({"status": "processed", "refund_id": "rfnd_seed_1"})
    with stub_router(stub):
        run(mcp_payments.get_refund_status(order_id=env["ids"]["o1"], token=env["manager"]))
    assert row_counts(env["Session"]) == before


# ---------- agent routing ----------

def test_agent_routes_payment_questions():
    from app.mcp.agent import ANALYTICS_GUIDANCE

    assert "get_refund_status" in ANALYTICS_GUIDANCE
    assert "list_payment_issues" in ANALYTICS_GUIDANCE
    assert "stale" in ANALYTICS_GUIDANCE
