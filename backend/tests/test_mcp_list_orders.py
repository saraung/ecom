# tests/test_mcp_list_orders.py
"""Real read-only list_orders MCP tool (isolated sqlite DB).

Covers: success + filters + limit/offset + server-side max clamp +
validation errors + 401/403 paths + empty results + field whitelist +
fake-tool removal + get_order regression + DB-side filtering proof.
"""
import asyncio
import json
import os
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from app.core.config import settings

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.models.order import Order, OrderStatus  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.orders as mcp_orders  # noqa: E402
import app.repositories.order as order_repo  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_list_orders_test.db"
PASSWORD = "TestPass123"

EXPECTED_FIELDS = {
    "id",
    "order_number",
    "status",
    "payment_status",
    "grand_total",
    "placed_at",
    "user_id",
}


def _seed_rbac(session: Session) -> None:
    for key, label, module, description in PERMISSIONS:
        session.add(
            Permission(key=key, label=label, module=module, description=description)
        )
    session.flush()
    perms = {p.key: p for p in session.exec(select(Permission)).all()}
    for slug, spec in SYSTEM_ROLES.items():
        role = Role(
            name=spec["name"], slug=slug, description=spec["description"], is_system=True
        )
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


def _make_order(session: Session, owner: User, idx: int, status, payment: str) -> Order:
    order = Order(
        order_number=f"ORD-TEST-{idx:05d}",
        user_id=owner.id,
        shipping_address_id=uuid4(),
        billing_address_id=uuid4(),
        subtotal=Decimal("100.00"),
        grand_total=Decimal("100.00"),
        status=status,
        payment_status=payment,
    )
    session.add(order)
    return order


@pytest.fixture(scope="module")
def env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)

    # The MCP tools open their own Session(engine) — point all three at sqlite.
    # (Module scope can't use the function-scoped `monkeypatch` fixture,
    # so patch/restore manually.)
    originals = (mcp_auth.engine, mcp_guards.engine, mcp_orders.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_orders.engine = test_engine

    with TestingSession() as s:
        _seed_rbac(s)
        staff = _make_user(s, "staffer@mcp-test.com", UserRole.staff)
        admin = _make_user(s, "admin@mcp-test.com", UserRole.admin)
        customer = _make_user(s, "shopper@mcp-test.com", UserRole.customer)
        for i in range(50):  # 50 x pending/paid
            _make_order(s, customer, i, OrderStatus.PENDING, "paid")
        for i in range(50, 55):  # 5 x confirmed/paid
            _make_order(s, customer, i, OrderStatus.CONFIRMED, "paid")
        for i in range(55, 58):  # 3 x shipped/cod_pending
            _make_order(s, customer, i, OrderStatus.SHIPPED, "cod_pending")
        for i in range(58, 60):  # 2 x delivered/refund_completed
            _make_order(s, customer, i, OrderStatus.DELIVERED, "refund_completed")
        s.commit()
        sample = s.exec(select(Order).limit(1)).first()
        sample_id, sample_number = str(sample.id), sample.order_number

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email,
            role=user.role.value,
            audience=audience,
            token_version=user.token_version,
        )

    try:
        yield {
            "staff": token_for(staff),
            "admin": token_for(admin),
            "customer": token_for(customer),
            "staff_storefront": token_for(staff, audience="storefront"),
            "sample_id": sample_id,
            "sample_number": sample_number,
        }
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_orders.engine = originals


def run(coro):
    return asyncio.run(coro)


# 1. valid staff/admin JWT + orders.view -> list orders
def test_list_orders_staff_success(env):
    res = run(mcp_orders.list_orders(token=env["staff"]))
    assert res["success"] is True
    assert res["returned_count"] == 20  # default limit
    assert res["total_matching"] == 60
    assert res["limit"] == 20 and res["offset"] == 0


def test_list_orders_admin_success(env):
    res = run(mcp_orders.list_orders(limit=5, token=env["admin"]))
    assert res["success"] is True and res["returned_count"] == 5


# 2. status filter
def test_status_filter(env):
    res = run(mcp_orders.list_orders(status="pending", limit=50, token=env["staff"]))
    assert res["success"] is True
    assert res["total_matching"] == 50
    assert res["returned_count"] == 50
    assert {o["status"] for o in res["orders"]} == {"pending"}


# 3. payment_status filter
def test_payment_status_filter(env):
    res = run(mcp_orders.list_orders(payment_status="cod_pending", token=env["staff"]))
    assert res["success"] is True
    assert res["total_matching"] == 3 and res["returned_count"] == 3
    assert {o["payment_status"] for o in res["orders"]} == {"cod_pending"}


# 3b. date filters (all seeded orders share today's placed_at)
def test_date_filter_today(env):
    today = date.today().isoformat()
    res = run(mcp_orders.list_orders(from_date=today, to_date=today, limit=50, token=env["staff"]))
    assert res["success"] is True
    assert res["total_matching"] == 60 and res["returned_count"] == 50
    assert res["from_date"] == today and res["to_date"] == today


def test_date_filter_future_empty(env):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = run(mcp_orders.list_orders(from_date=tomorrow, token=env["staff"]))
    assert res["success"] is True
    assert res["orders"] == [] and res["total_matching"] == 0


def test_date_filter_invalid(env):
    res = run(mcp_orders.list_orders(from_date="not-a-date", token=env["staff"]))
    assert res["success"] is False and "YYYY-MM-DD" in res["error"]
    res = run(mcp_orders.list_orders(to_date="12/10/2026", token=env["staff"]))
    assert res["success"] is False and "YYYY-MM-DD" in res["error"]
    res = run(
        mcp_orders.list_orders(
            from_date=(date.today() + timedelta(days=1)).isoformat(),
            to_date=date.today().isoformat(),
            token=env["staff"],
        )
    )
    assert res["success"] is False and "must not be after" in res["error"]


# 4. limit/offset
def test_limit_offset(env):
    first = run(mcp_orders.list_orders(limit=5, offset=0, token=env["staff"]))
    second = run(mcp_orders.list_orders(limit=5, offset=58, token=env["staff"]))
    assert first["returned_count"] == 5 and first["total_matching"] == 60
    assert second["returned_count"] == 2  # only 60 total
    assert {o["id"] for o in first["orders"]}.isdisjoint({o["id"] for o in second["orders"]})


# 5. maximum limit is enforced server-side
def test_max_limit_enforced(env):
    res = run(mcp_orders.list_orders(limit=10000, token=env["staff"]))
    assert res["limit"] == mcp_orders.MAX_LIST_LIMIT == 50
    assert res["returned_count"] == 50  # seeded 60 > max proves the clamp


# 6. invalid status/payment_status -> validation error
def test_invalid_status(env):
    res = run(mcp_orders.list_orders(status="bogus", token=env["staff"]))
    assert res["success"] is False and "Invalid status" in res["error"]


def test_invalid_payment_status(env):
    res = run(mcp_orders.list_orders(payment_status="bogus", token=env["staff"]))
    assert res["success"] is False and "Invalid payment_status" in res["error"]


# 7. customer JWT -> 403
def test_customer_forbidden(env):
    res = run(mcp_orders.list_orders(token=env["customer"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


# 8. invalid JWT -> 401
def test_invalid_jwt(env):
    res = run(mcp_orders.list_orders(token="bad.jwt.here"))
    assert res["success"] is False


# 9. storefront audience -> 403
def test_storefront_forbidden(env):
    res = run(mcp_orders.list_orders(token=env["staff_storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


# 10. empty result -> valid empty response
def test_empty_result(env):
    res = run(mcp_orders.list_orders(status="rto", token=env["staff"]))
    assert res["success"] is True
    assert res["orders"] == [] and res["returned_count"] == 0 and res["total_matching"] == 0


# 11. returned fields contain no sensitive/unrequested fields
def test_field_whitelist(env):
    res = run(mcp_orders.list_orders(limit=3, token=env["staff"]))
    assert res["success"] is True
    for order in res["orders"]:
        assert set(order.keys()) == EXPECTED_FIELDS
    blob = str(res["orders"]).lower()
    for leaked in ("snapshot", "refund_id", "awb", "courier", "address", "password", "secret"):
        assert leaked not in blob


# 15. LLM-facing tool schemas stay within a prompt budget. Every char is
# re-sent on every agent turn, so long docstrings regress latency; the
# heaviest tools carry explicit short descriptions (see app/mcp/server.py).
# Budget grew from 14,500 to 16,000 when adjust_stock joined the tool set;
# it remains a regression guard, not a target.
def test_tool_schema_budget():
    tools = run(mcp.list_tools())
    total = sum(
        len(t.name or "")
        + len(t.description or "")
        + len(json.dumps(t.input_schema or {}))
        for t in tools
    )
    assert total < 16000, f"tool schema payload {total} chars exceeds budget"


# 12. fake tools are no longer registered
def test_registered_tools():
    names = run(mcp.list_tools())
    names = {t.name for t in names}
    assert names == {"whoami", "check_orders_view", "get_order", "list_orders", "cancel_order", "issue_refund",
                      "list_products", "get_product", "compare_products", "update_product",
                      "update_product_price", "delete_product", "check_stock",
                      "check_product_inventory", "adjust_stock", "list_low_stock_products",
                      "sales_summary", "sales_trend", "product_performance",
                      "get_payment_status", "list_refunds", "list_payment_issues",
                      "get_refund_status"}
    for fake in ("get_all_orders", "find_customer", "get_customer_orders", "test_failure"):
        assert fake not in names


# 13. existing get_order still passes
def test_get_order_regression(env):
    from app.core.region import currency_code

    by_id = run(mcp_orders.get_order(env["sample_id"], token=env["staff"]))
    by_number = run(mcp_orders.get_order(env["sample_number"], token=env["staff"]))
    assert by_id["success"] is True and by_id["order"]["id"] == env["sample_id"]
    assert "item_count" in by_id["order"]  # get_order shape unchanged
    assert by_number["success"] is True
    assert by_number["order"]["order_number"] == env["sample_number"]
    # Money envelopes carry the live deployment currency (never assumed).
    assert by_id["currency"] == currency_code()
    listed = run(mcp_orders.list_orders(limit=1, token=env["staff"]))
    assert listed["currency"] == currency_code()


# 14. filtering/pagination happens in the repository (DB-side), never unbounded
def test_filtering_happens_db_side(env, monkeypatch):
    seen = {}

    real_fn = mcp_orders.get_all_orders_with_filters

    def spy(session, **kwargs):
        seen.update(kwargs)
        return real_fn(session, **kwargs)

    def bomb(*args, **kwargs):  # the unbounded loader must never run
        raise AssertionError("unbounded get_all_orders was called")

    monkeypatch.setattr(mcp_orders, "get_all_orders_with_filters", spy)
    monkeypatch.setattr(order_repo, "get_all_orders", bomb)

    res = run(
        mcp_orders.list_orders(
            status="pending", payment_status="paid", limit=7, offset=3, token=env["staff"]
        )
    )
    assert res["success"] is True and res["returned_count"] == 7
    assert seen["status"] == OrderStatus.PENDING
    assert seen["payment_status"] == "paid"
    assert seen["skip"] == 3 and seen["limit"] == 7

    # And the server-side clamp reaches the repository, not Python slicing.
    seen.clear()
    res = run(mcp_orders.list_orders(limit=10000, token=env["staff"]))
    assert seen["limit"] == mcp_orders.MAX_LIST_LIMIT
    assert res["returned_count"] == mcp_orders.MAX_LIST_LIMIT
