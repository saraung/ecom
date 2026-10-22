# tests/test_mcp_analytics.py
"""MCP sales & analytics tools (isolated sqlite DB).

All figures come from database-side aggregation reusing
repositories/analytics.py. Covers presets/ranges, UTC-day grouping,
status inclusion rules, COD handling, partial refunds, comparisons,
all four product views, permission enforcement, and registration.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
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
from app.models.category import Category  # noqa: E402
from app.models.order import Order, OrderItem, OrderStatus  # noqa: E402
from app.models.payment import Payment, PaymentProvider, PaymentStatus  # noqa: E402
from app.models.product import Product, ProductVariant  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.refund import Refund, RefundStatus  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.analytics as mcp_analytics  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_analytics_test.db"
PASSWORD = "TestPass123"
NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


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

    originals = (mcp_auth.engine, mcp_guards.engine, mcp_analytics.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_analytics.engine = test_engine

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email, role=user.role.value, audience=audience,
            token_version=user.token_version,
        )

    try:
        with TestingSession() as s:
            _seed_rbac(s)
            manager = _make_user(s, "manager@mcp-an.com", UserRole.manager)
            staff = _make_user(s, "staff@mcp-an.com", UserRole.staff)
            customer = _make_user(s, "shopper@mcp-an.com", UserRole.customer)

            cat_a = Category(name="Cat A", slug="cat-a")
            cat_b = Category(name="Cat B", slug="cat-b")
            s.add(cat_a)
            s.add(cat_b)
            s.commit()
            s.refresh(cat_a)
            s.refresh(cat_b)

            def product(name, slug, cat, price="100.00"):
                p = Product(name=name, slug=slug, price=Decimal(price),
                            category_id=cat.id)
                s.add(p)
                s.commit()
                s.refresh(p)
                return p

            def variant(product, sku, stock=10, price=None):
                v = ProductVariant(product_id=product.id, sku=sku, stock=stock,
                                   price_override=Decimal(price) if price else None,
                                   attributes={})
                s.add(v)
                s.commit()
                s.refresh(v)
                return v

            pa1 = product("An A1", "an-a1", cat_a, "100.00")
            va1 = variant(pa1, "AN-A1")
            va2 = variant(pa1, "AN-A2")
            pb1 = product("An B1", "an-b1", cat_b, "200.00")
            vb1 = variant(pb1, "AN-B1")
            pslow = product("An Slow", "an-slow", cat_a, "50.00")
            variant(pslow, "AN-SLOW")
            pdecl = product("An Decl", "an-decl", cat_b, "50.00")
            vdecl = variant(pdecl, "AN-DECL")

            def order(number, status, method, pay_status, grand, placed, refund=Decimal("0")):
                o = Order(
                    order_number=number, user_id=customer.id,
                    shipping_address_id=uuid4(), billing_address_id=uuid4(),
                    subtotal=Decimal(grand), grand_total=Decimal(grand),
                    status=status, payment_method=method, payment_status=pay_status,
                    refund_amount=Decimal(refund), placed_at=placed,
                )
                s.add(o)
                s.commit()
                s.refresh(o)
                return o

            def item(order, var, qty, unit):
                s.add(OrderItem(order_id=order.id, variant_id=var.id,
                                product_name="x", variant_sku=var.sku,
                                variant_attributes={}, quantity=qty,
                                unit_price=Decimal(unit),
                                line_total=Decimal(unit) * qty))
                s.commit()

            def pay(order, amount, status=PaymentStatus.SUCCEEDED, intent="pay_x"):
                s.add(Payment(order_id=order.id, provider=PaymentProvider.RAZORPAY,
                              provider_payment_id=f"order_{order.order_number}",
                              provider_payment_intent=intent,
                              amount=Decimal(amount), currency="INR", status=status))
                s.commit()

            o1 = order("AN-001", OrderStatus.CONFIRMED, "online", "paid", "1000.00", NOW)
            item(o1, va1, 2, "100.00")
            item(o1, va2, 1, "100.00")
            item(o1, vdecl, 1, "50.00")
            pay(o1, "1000.00", intent="pay_1")
            o2 = order("AN-002", OrderStatus.DELIVERED, "online", "paid", "2000.00",
                       NOW - timedelta(days=2), refund="500.00")
            item(o2, va1, 1, "100.00")
            item(o2, vb1, 3, "200.00")
            pay(o2, "2000.00", intent="pay_2")
            pay(o2, "2000.00", status=PaymentStatus.FAILED, intent="pay_2b")
            order("AN-003", OrderStatus.PENDING, "online", "pending", "500.00", NOW)
            order("AN-004", OrderStatus.CANCELLED, "online", "paid", "800.00",
                  NOW - timedelta(days=1))
            order("AN-005", OrderStatus.CONFIRMED, "cod", "cod_pending", "300.00", NOW)
            o6 = order("AN-006", OrderStatus.DELIVERED, "online", "paid", "500.00",
                       NOW - timedelta(days=10))
            item(o6, vdecl, 10, "50.00")
            pay(o6, "500.00", intent="pay_6")
            o7 = order("AN-007", OrderStatus.CONFIRMED, "online", "paid", "100.00", NOW)
            pay(o7, "100.00", intent="pay_7")
            s.add(Refund(order_id=o2.id, amount=Decimal("500.00"),
                         idempotency_key="seed-exec-1", status=RefundStatus.EXECUTED,
                         reason="t", requested_by=manager.id))
            s.add(Refund(order_id=o6.id, amount=Decimal("50.00"),
                         idempotency_key="seed-pend-1", status=RefundStatus.PENDING_APPROVAL,
                         reason="t", requested_by=manager.id))
            s.commit()

        yield {
            "manager": token_for(manager), "staff": token_for(staff),
            "customer": token_for(customer),
            "storefront": token_for(manager, audience="storefront"),
        }
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_analytics.engine = originals


def run(coro):
    return asyncio.run(coro)


# ---------- registration ----------

def test_registered_analytics_tools():
    names = {t.name for t in run(mcp.list_tools())}
    assert {"sales_summary", "sales_trend", "product_performance"} <= names


# ---------- permissions ----------

def test_analytics_auth_matrix(env):
    assert run(mcp_analytics.sales_summary(token=env["customer"])) == {
        "success": False, "error": "Insufficient permissions"}
    assert run(mcp_analytics.sales_summary(token=env["staff"])) == {
        "success": False, "error": "Insufficient permissions"}
    assert run(mcp_analytics.sales_summary(token="bad"))["success"] is False
    res = run(mcp_analytics.sales_summary(token=env["storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


# ---------- sales_summary ----------

def test_summary_last_7(env):
    from app.core.region import currency_code

    res = run(mcp_analytics.sales_summary(token=env["manager"]))
    assert res["success"] is True
    assert res["currency"] == currency_code()
    assert res["period"]["to"] == datetime.now(timezone.utc).date().isoformat()
    s = res["summary"]
    # settled: o1 (1000) + o2 (2000-500) + o7 (100); o4 cancelled excluded
    assert s["revenue"] == 2600.0 and s["orders"] == 3
    assert s["average_order_value"] == pytest.approx(2600.0 / 3)
    assert s["collected"] == 3100.0 and s["refunded"] == 500.0
    by_status = {b["status"]: b for b in s["by_status"]}
    assert by_status["pending"]["revenue"] == 0 and by_status["pending"]["count"] == 1
    assert by_status["cancelled"]["revenue"] == 0
    assert s["total_orders_any_status"] == 6  # o1,o2,o3,o4,o5,o7 (o6 outside window)
    pay = {p["status"]: p for p in s["payments_by_status"]}
    assert pay["succeeded"]["count"] == 3 and pay["succeeded"]["amount"] == 3100.0
    assert pay["failed"]["count"] == 1  # multi-attempt rows counted per record
    led = {r["status"]: r for r in s["refund_ledger_by_status"]}
    assert led["executed"]["amount"] == 500.0
    assert res["comparison"] is not None
    assert res["comparison"]["previous_to"] < res["period"]["from"]


def test_summary_today_and_yesterday(env):
    today = run(mcp_analytics.sales_summary(preset="today", token=env["manager"]))
    assert today["summary"]["revenue"] == 1100.0
    assert today["summary"]["orders"] == 2
    yest = run(mcp_analytics.sales_summary(preset="yesterday", token=env["manager"]))
    assert yest["summary"]["revenue"] == 0 and yest["summary"]["orders"] == 0
    assert yest["summary"]["total_orders_any_status"] == 1  # cancelled o4 only


def test_summary_custom_range_and_validation(env):
    today = datetime.now(timezone.utc).date()
    res = run(mcp_analytics.sales_summary(
        preset=None, from_date=(today - timedelta(days=2)).isoformat(),
        to_date=today.isoformat(), compare=False, token=env["manager"]))
    assert res["success"] is True and res["comparison"] is None
    assert res["summary"]["revenue"] == 2600.0
    assert run(mcp_analytics.sales_summary(preset="nope", token=env["manager"]))["success"] is False
    assert run(mcp_analytics.sales_summary(
        preset=None, from_date="2026-02-01", to_date="2026-01-01",
        token=env["manager"]))["error"].startswith("from_date must not be after")
    assert "exceed" in run(mcp_analytics.sales_summary(
        preset=None, from_date="2020-01-01", to_date="2026-01-01",
        token=env["manager"]))["error"]
    assert "YYYY-MM-DD" in run(mcp_analytics.sales_summary(
        preset=None, from_date="x", to_date="2026-01-01",
        token=env["manager"]))["error"]


def test_summary_comparison_math(env):
    res = run(mcp_analytics.sales_summary(preset="last_7", token=env["manager"]))
    comp = res["comparison"]
    # previous 7-day window holds only o6 (500 net)
    assert comp["revenue"] == 500.0 and comp["orders"] == 1
    assert comp["revenue_change_pct"] == pytest.approx((2600 - 500) / 500 * 100)
    # zero base -> null, never invented
    empty = run(mcp_analytics.sales_summary(
        preset=None, from_date="2020-01-01", to_date="2020-01-07", token=env["manager"]))
    assert empty["summary"]["revenue"] == 0
    assert empty["comparison"]["revenue_change_pct"] is None


# ---------- sales_trend ----------

def test_trend_zero_filled_days(env):
    res = run(mcp_analytics.sales_trend(token=env["manager"]))
    assert res["success"] is True and res["point_count"] == 7
    assert sum(p["orders"] for p in res["points"]) == 3
    assert sum(p["revenue"] for p in res["points"]) == pytest.approx(2600.0)
    assert run(mcp_analytics.sales_trend(group_by="nope", token=env["manager"]))["success"] is False
    weekly = run(mcp_analytics.sales_trend(group_by="week", token=env["manager"]))
    assert weekly["success"] is True and weekly["point_count"] >= 1
    monthly = run(mcp_analytics.sales_trend(group_by="month", token=env["manager"]))
    assert monthly["success"] is True


# ---------- product_performance ----------

def test_top_views_and_fanout(env):
    units = run(mcp_analytics.product_performance(view="top_units", token=env["manager"]))
    assert units["success"] is True
    qtys = [p["total_quantity_sold"] for p in units["products"]]
    assert qtys == sorted(qtys, reverse=True) and qtys[0] == 11  # V-DECL 10+1
    rev = run(mcp_analytics.product_performance(view="top_revenue", token=env["manager"]))
    revs = [p["total_revenue"] for p in rev["products"]]
    assert revs == sorted(revs, reverse=True)
    # join fan-out check: P-A1 spans o1+o7 = 2 distinct orders, not 3 rows
    a1 = next(p for p in units["products"] if p["product_slug"] == "an-a1")
    assert a1["order_count"] == 2
    assert run(mcp_analytics.product_performance(view="nope", token=env["manager"]))["success"] is False
    assert run(mcp_analytics.product_performance(limit=10000, token=env["manager"]))["limit"] == 50


def test_category_slow_declining(env):
    cats = run(mcp_analytics.product_performance(view="by_category", token=env["manager"]))
    assert cats["success"] is True and cats["returned_count"] == 2
    assert cats["categories"][0]["revenue"] >= cats["categories"][1]["revenue"]
    slow = run(mcp_analytics.product_performance(view="slow", token=env["manager"]))
    assert slow["success"] is True
    slow_slugs = {p["product_slug"] for p in slow["products"]}
    assert "an-slow" in slow_slugs and "an-a1" not in slow_slugs
    never = next(p for p in slow["products"] if p["product_slug"] == "an-slow")
    assert never["last_sale_date"] is None
    decl = run(mcp_analytics.product_performance(view="declining", days=7, token=env["manager"]))
    assert decl["success"] is True
    assert decl["rule"] == {"window_days": 7, "min_prior_units": 5, "drop_pct": 0.5}
    found = next(p for p in decl["products"] if p["product_name"] == "An Decl")
    assert (found["prior_units"], found["recent_units"], found["drop_pct"]) == (10, 1, 90.0)
    assert run(mcp_analytics.product_performance(view="declining", drop_pct=5, token=env["manager"]))["success"] is False
    assert run(mcp_analytics.product_performance(view="declining", min_prior_units=0, token=env["manager"]))["success"] is False


def test_explicit_dates_override_default_preset(env):
    # Fixtures are seeded relative to NOW, so a hard-coded calendar month
    # silently expires. A 14-day window includes the NOW-10 order, which the
    # default last_7 preset would exclude — that is what proves the override.
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=14)).isoformat()
    to_date = today.isoformat()
    res = run(mcp_analytics.sales_summary(
        from_date=from_date, to_date=to_date, token=env["manager"]))
    assert res["success"] is True
    assert res["period"]["from"] == from_date
    assert res["period"]["to"] == to_date
    assert res["summary"]["orders"] > 0


def test_explicit_preset_without_dates_still_applies(env):
    res = run(mcp_analytics.sales_summary(preset="today", token=env["manager"]))
    assert res["success"] is True
    today = datetime.now(timezone.utc).date().isoformat()
    assert res["period"] == {"from": today, "to": today, "utc": True}


def test_invalid_explicit_date_surfaced(env):
    res = run(mcp_analytics.sales_summary(
        from_date="not-a-date", to_date="2026-09-30", token=env["manager"]))
    assert res["success"] is False and "YYYY-MM-DD" in res["error"]


def test_month_guidance_mentions_explicit_ranges():
    from app.mcp.agent import ANALYTICS_GUIDANCE

    assert "preset=null" in ANALYTICS_GUIDANCE
    assert "explicit" in ANALYTICS_GUIDANCE
