# tests/test_mcp_products.py
"""MCP product + inventory tools (isolated sqlite DB).

Reads reuse repositories/product.py; writes preview first (signed token
binding user + target + exact changes + live fingerprint) and execute only
with confirmed=true under a row lock. Covers registration, search/filter/
pagination, comparisons, low-stock, per-write permission denial, the full
preview/confirm/replay matrix, audit rows, RAG hooks, and rollback.
"""
import asyncio
import os
from decimal import Decimal
from unittest import mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
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
from app.models.product import Product, ProductVariant  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink, UserRoleLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402
from app.services import rag_service  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.inventory as mcp_inventory  # noqa: E402
import app.mcp.tools.products as mcp_products  # noqa: E402
from app.mcp.server import mcp  # noqa: E402

TEST_DB = "/tmp/mcp_products_test.db"
PASSWORD = "TestPass123"

EXPECTED_PRODUCT_TOOLS = {
    "list_products", "get_product", "compare_products",
    "update_product", "update_product_price", "delete_product",
}
EXPECTED_INVENTORY_TOOLS = {
    "check_stock", "check_product_inventory", "adjust_stock", "list_low_stock_products",
}


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


def _make_product(session: Session, name: str, slug: str, price: str, active=True) -> Product:
    product = Product(name=name, slug=slug, price=Decimal(price), is_active=active)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def _make_variant(session: Session, product: Product, sku: str, stock: int,
                  override: str | None = None, attributes=None) -> ProductVariant:
    variant = ProductVariant(
        product_id=product.id, sku=sku, stock=stock,
        price_override=Decimal(override) if override else None,
        attributes=attributes or {},
    )
    session.add(variant)
    session.commit()
    session.refresh(variant)
    return variant


@pytest.fixture(scope="module")
def env():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine, class_=Session, expire_on_commit=False)

    originals = (mcp_auth.engine, mcp_guards.engine,
                 mcp_products.engine, mcp_inventory.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_products.engine = test_engine
    mcp_inventory.engine = test_engine
    rag_ingest = mock.patch.object(rag_service, "ingest_all_products", return_value=1)
    rag_delete = mock.patch.object(rag_service, "delete_product_from_rag", return_value=True)
    rag_ingest.start()
    rag_delete.start()

    with TestingSession() as s:
        _seed_rbac(s)
        manager = _make_user(s, "manager@mcp-prod.com", UserRole.manager)
        admin = _make_user(s, "admin@mcp-prod.com", UserRole.admin)
        staff = _make_user(s, "staff@mcp-prod.com", UserRole.staff)
        customer = _make_user(s, "shopper@mcp-prod.com", UserRole.customer)
        p1 = _make_product(s, "MCP Widget", "mcp-widget", "120.00")
        v1 = _make_variant(s, p1, "MCP-SKU-1", 10, override="99.99",
                           attributes={"size": "M"})
        v2 = _make_variant(s, p1, "MCP-SKU-2", 3)
        _make_product(s, "MCP Retired", "mcp-retired", "50.00", active=False)
        p3 = _make_product(s, "MCP Empty", "mcp-empty", "10.00")
        _make_variant(s, p3, "MCP-SKU-3", 0)
        p4 = _make_product(s, "MCP Doomed", "mcp-doomed", "20.00")
        ids = {
            "p1": str(p1.id), "v1": str(v1.id), "v2": str(v2.id),
            "p4": str(p4.id),
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
                "client": client, "Session": TestingSession,
                "manager": token_for(manager), "admin": token_for(admin),
                "staff": token_for(staff), "customer": token_for(customer),
                "storefront": token_for(manager, audience="storefront"),
                "ids": ids,
            }
    finally:
        app.dependency_overrides.clear()
        (mcp_auth.engine, mcp_guards.engine,
         mcp_products.engine, mcp_inventory.engine) = originals
        rag_ingest.stop()
        rag_delete.stop()


def run(coro):
    return asyncio.run(coro)


def audits(Session, action):
    with Session() as s:
        return s.exec(select(AdminAuditLog).where(AdminAuditLog.action == action)).all()


# ---------- registration ----------

def test_registered_product_tools():
    names = {t.name for t in run(mcp.list_tools())}
    assert EXPECTED_PRODUCT_TOOLS <= names
    assert EXPECTED_INVENTORY_TOOLS <= names


# ---------- reads ----------

def test_list_products_default(env):
    from app.core.region import currency_code

    res = run(mcp_products.list_products(token=env["manager"]))
    assert res["success"] is True and res["total_matching"] == 4
    assert res["returned_count"] == 4 and res["limit"] == 20
    assert res["currency"] == currency_code()


def test_list_products_search_and_active(env):
    res = run(mcp_products.list_products(search="widget", token=env["manager"]))
    assert res["total_matching"] == 1 and res["products"][0]["slug"] == "mcp-widget"
    res = run(mcp_products.list_products(is_active=False, token=env["manager"]))
    assert res["total_matching"] == 1


def test_list_products_pagination_clamp(env):
    res = run(mcp_products.list_products(limit=10000, token=env["manager"]))
    assert res["limit"] == 50 and res["returned_count"] == 4
    assert run(mcp_products.list_products(limit="x", token=env["manager"]))["success"] is False


def test_list_products_price_sort(env):
    asc = run(mcp_products.list_products(sort_by="price", sort_dir="asc", token=env["manager"]))
    assert asc["success"] is True
    prices = [float(p["price"]) for p in asc["products"]]
    assert prices == sorted(prices)
    assert asc["sort_by"] == "price" and asc["sort_dir"] == "asc"
    cheapest = run(mcp_products.list_products(sort_by="price", sort_dir="asc", limit=1, token=env["manager"]))
    assert cheapest["returned_count"] == 1
    assert float(cheapest["products"][0]["price"]) == min(prices)
    desc = run(mcp_products.list_products(sort_by="price", sort_dir="desc", token=env["manager"]))
    assert [float(p["price"]) for p in desc["products"]] == sorted(prices, reverse=True)
    assert run(mcp_products.list_products(sort_by="bogus", token=env["manager"]))["success"] is False
    assert run(mcp_products.list_products(sort_dir="sideways", token=env["manager"]))["success"] is False


def test_list_products_default_order_unchanged(env):
    default = run(mcp_products.list_products(token=env["manager"]))
    explicit = run(
        mcp_products.list_products(sort_by="created_at", sort_dir="desc", token=env["manager"])
    )
    assert [p["id"] for p in default["products"]] == [p["id"] for p in explicit["products"]]


def test_get_product_lookups(env):
    by_id = run(mcp_products.get_product(env["ids"]["p1"], token=env["manager"]))
    by_slug = run(mcp_products.get_product("mcp-widget", token=env["manager"]))
    by_sku = run(mcp_products.get_product("MCP-SKU-1", token=env["manager"]))
    for res in (by_id, by_slug, by_sku):
        assert res["success"] is True and res["product"]["slug"] == "mcp-widget"
    assert len(by_id["product"]["variants"]) == 2
    assert run(mcp_products.get_product("nope", token=env["manager"]))["success"] is False


def test_compare_products(env):
    res = run(mcp_products.compare_products(["mcp-widget", "mcp-empty"], token=env["manager"]))
    assert res["success"] is True and res["compared_count"] == 2
    assert res["products"][0]["price"] == "120.00"
    assert run(mcp_products.compare_products(["mcp-widget"] * 6, token=env["manager"]))["success"] is False
    assert run(mcp_products.compare_products(["mcp-widget", "nope"], token=env["manager"]))["success"] is False


def test_check_stock_and_inventory(env):
    sku = run(mcp_inventory.check_stock("MCP-SKU-1", token=env["manager"]))
    assert sku["success"] is True and sku["variant"]["stock"] == 10
    assert sku["variant"]["effective_price"] == "99.99"
    prod = run(mcp_inventory.check_stock(env["ids"]["p1"], token=env["manager"]))
    assert prod["success"] is True and prod["total_stock"] == 13
    inv = run(mcp_inventory.check_product_inventory(env["ids"]["p1"], token=env["manager"]))
    assert inv["availability"] == "in_stock"
    empty = run(mcp_inventory.check_product_inventory("mcp-empty", token=env["manager"]))
    assert empty["availability"] == "out_of_stock"
    assert run(mcp_inventory.check_stock("nope", token=env["manager"]))["success"] is False


def test_low_stock(env):
    res = run(mcp_inventory.list_low_stock_products(token=env["manager"]))
    assert res["success"] is True and res["threshold"] == 5
    assert res["total_matching"] == 2  # V2 (3) and V3 (0)
    assert res["variants"][0]["stock"] == 0  # ascending
    zero = run(mcp_inventory.list_low_stock_products(threshold=0, token=env["manager"]))
    assert zero["total_matching"] == 1
    page = run(mcp_inventory.list_low_stock_products(limit=1, offset=1, token=env["manager"]))
    assert page["returned_count"] == 1 and page["total_matching"] == 2
    assert run(mcp_inventory.list_low_stock_products(threshold=-1, token=env["manager"]))["success"] is False


def test_read_auth_matrix(env):
    assert run(mcp_products.list_products(token=env["customer"]))["error"] == "Insufficient permissions"
    assert run(mcp_inventory.check_stock("MCP-SKU-1", token="bad"))["success"] is False
    res = run(mcp_products.list_products(token=env["storefront"]))
    assert res["success"] is False and "admin panel" in res["error"]


# ---------- update_product ----------

def test_update_preview_no_write(env):
    oid = env["ids"]["p1"]
    with env["Session"]() as s:
        before = s.get(Product, __import__("uuid").UUID(oid)).name
    res = run(mcp_products.update_product(oid, {"name": "Renamed"}, token=env["manager"]))
    assert res["success"] is True and res["requires_confirmation"] is True
    assert res["changes"] == {"name": "Renamed"} and res["preview_token"]
    with env["Session"]() as s:
        assert s.get(Product, __import__("uuid").UUID(oid)).name == before


def test_update_validation(env):
    oid = env["ids"]["p1"]
    assert "Unsupported fields" in run(mcp_products.update_product(
        oid, {"price": "9"}, token=env["manager"]))["error"]
    assert "Unsupported fields" in run(mcp_products.update_product(
        oid, {"slug": "x"}, token=env["manager"]))["error"]
    assert run(mcp_products.update_product(oid, {"name": ""}, token=env["manager"]))["success"] is False
    assert "UUID" in run(mcp_products.update_product(
        oid, {"category_id": "nope"}, token=env["manager"]))["error"]
    assert "does not exist" in run(mcp_products.update_product(
        oid, {"category_id": str(uuid4())}, token=env["manager"]))["error"]


def test_update_execute_and_replay(env):
    from uuid import UUID as _UUID

    oid = env["ids"]["p1"]
    pre = run(mcp_products.update_product(oid, {"name": "Renamed"}, token=env["manager"]))
    res = run(mcp_products.update_product(
        oid, {"name": "Renamed"}, preview_token=pre["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["product"]["name"] == "Renamed"
    assert rag_service.ingest_all_products.called
    assert len(audits(env["Session"], "product.updated")) >= 1
    again = run(mcp_products.update_product(
        oid, {"name": "Renamed"}, preview_token=pre["preview_token"],
        confirmed=True, token=env["manager"]))
    assert again["success"] is False and "stale" in again["error"].lower()


def test_update_perm_denied(env):
    oid = env["ids"]["p1"]
    assert run(mcp_products.update_product(
        oid, {"name": "X"}, token=env["customer"]))["error"] == "Insufficient permissions"


# ---------- price ----------

def test_price_preview_execute(env):
    pre = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="140.00", token=env["manager"]))
    assert pre["success"] is True and pre["changes"] == {"price": "140.00"}
    res = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="140.00", preview_token=pre["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["product"]["price"] == "140.00"


def test_price_validation_and_variant(env):
    assert "positive" in run(mcp_products.update_product_price(
        env["ids"]["p1"], price="0", token=env["manager"]))["error"]
    assert "positive" in run(mcp_products.update_product_price(
        env["ids"]["p1"], price="abc", token=env["manager"]))["error"]
    pre = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="88.00", variant_id="MCP-SKU-2", token=env["manager"]))
    assert pre["success"] is True
    res = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="88.00", variant_id="MCP-SKU-2",
        preview_token=pre["preview_token"], confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["variant"]["sku"] == "MCP-SKU-2"


def test_price_perm_mirrors_ui(env):
    # staff holds products.update (the UI price-edit key), so the agent
    # allows them too; customers holding nothing are still refused.
    pre = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="10.00", token=env["staff"]))
    assert pre["success"] is True and pre["requires_confirmation"] is True
    res = run(mcp_products.update_product_price(
        env["ids"]["p1"], price="10.00", token=env["customer"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


# ---------- delete (soft only) ----------

def test_delete_flow(env):
    oid = env["ids"]["p4"]
    pre = run(mcp_products.delete_product(oid, token=env["admin"]))
    assert pre["success"] is True and pre["requires_confirmation"] is True
    res = run(mcp_products.delete_product(
        oid, preview_token=pre["preview_token"], confirmed=True, token=env["admin"]))
    assert res["success"] is True and res["product"]["is_active"] is False
    assert rag_service.delete_product_from_rag.called
    assert len(audits(env["Session"], "product.deleted")) >= 1
    # still resolvable afterwards (soft, nothing physically removed)
    assert run(mcp_products.get_product(oid, token=env["admin"]))["success"] is True
    assert "already deactivated" in run(
        mcp_products.delete_product(oid, token=env["admin"]))["error"]


def test_delete_perm_denied(env):
    # manager deliberately lacks products.delete
    res = run(mcp_products.delete_product(env["ids"]["p1"], token=env["manager"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


# ---------- adjust_stock ----------

def test_adjust_preview_execute(env):
    pre = run(mcp_inventory.adjust_stock("MCP-SKU-1", 5, reason="recount", token=env["manager"]))
    assert pre["success"] is True and pre["resulting_stock"] == 15
    res = run(mcp_inventory.adjust_stock(
        "MCP-SKU-1", 5, reason="recount", preview_token=pre["preview_token"],
        confirmed=True, token=env["manager"]))
    assert res["success"] is True and res["variant"]["stock"] == 15
    assert res["previous_stock"] == 10
    assert len(audits(env["Session"], "product.updated")) >= 1
    again = run(mcp_inventory.adjust_stock(
        "MCP-SKU-1", 5, reason="recount", preview_token=pre["preview_token"],
        confirmed=True, token=env["manager"]))
    assert again["success"] is False and "stale" in again["error"].lower()


def test_adjust_validation(env):
    assert "negative" in run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", -5, reason="x", token=env["manager"]))["error"]
    assert "non-zero" in run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 0, reason="x", token=env["manager"]))["error"]
    assert "reason is required" in run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 1, reason="  ", token=env["manager"]))["error"]
    # staff holds products.update (the UI stock-edit key) so the agent
    # allows them; the customer holding nothing is still refused.
    pre = run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 1, reason="x", token=env["staff"]))
    assert pre["success"] is True and pre["requires_confirmation"] is True
    assert run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 1, reason="x", token=env["customer"])) == {
        "success": False, "error": "Insufficient permissions"}


def test_adjust_token_binding(env):
    pre = run(mcp_inventory.adjust_stock("MCP-SKU-2", 2, reason="r", token=env["manager"]))
    forged = "eyJhbGciOiJIUzI1NiJ9.e30.sig"
    assert "preview" in run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 2, reason="r", preview_token=forged,
        confirmed=True, token=env["manager"]))["error"].lower()
    other = run(mcp_inventory.adjust_stock(
        "MCP-SKU-2", 2, reason="r", preview_token=pre["preview_token"],
        confirmed=True, token=env["admin"]))
    assert other["success"] is False


# ---------- endpoint + order regression ----------

def test_endpoint_adjust(env):
    client = env["client"]
    assert client.post("/api/v1/mcp/inventory/adjust",
                       json={"variant_id": "x", "delta": 1, "reason": "r",
                             "preview_token": "y"}).status_code in (401, 403)
    pre = run(mcp_inventory.adjust_stock("MCP-SKU-2", 2, reason="shelf", token=env["manager"]))
    ok = client.post(
        "/api/v1/mcp/inventory/adjust",
        json={"variant_id": "MCP-SKU-2", "delta": 2, "reason": "shelf",
              "preview_token": pre["preview_token"]},
        headers={"Authorization": f"Bearer {env['manager']}"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["variant"]["stock"] == 5
    denied = client.post(
        "/api/v1/mcp/inventory/adjust",
        json={"variant_id": "MCP-SKU-2", "delta": 1, "reason": "s",
              "preview_token": pre["preview_token"]},
        headers={"Authorization": f"Bearer {env['customer']}"})
    assert denied.status_code == 400


def test_pending_action_for_writes():
    import json as _json
    from types import SimpleNamespace as _NS

    import app.mcp.agent as agent_mod

    seen = []

    async def fake_complete(messages, tools, stage="initial"):
        seen.append(([dict(m) for m in messages], tools))
        if len(seen) == 1:
            return _NS(choices=[_NS(message=_NS(
                content=None,
                tool_calls=[_NS(id="c1", function=_NS(
                    name="adjust_stock",
                    arguments=_json.dumps({"variant_id": "MCP-SKU-2", "delta": 2})))],
            ))])
        return _NS(choices=[_NS(message=_NS(content="done", tool_calls=[]))])

    orig_complete, orig_client = agent_mod._groq_complete, agent_mod.Client

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def list_tools(self):
            return _NS(tools=[_NS(
                name="adjust_stock", description="d",
                input_schema={"type": "object", "properties": {}})])

        async def call_tool(self, name, arguments):
            return _NS(content=[_NS(text=_json.dumps({
                "success": True, "requires_confirmation": True,
                "preview_token": "pt", "expires_in_minutes": 10,
                "variant": {"sku": "MCP-SKU-2"}, "delta": 2,
                "resulting_stock": 5, "reason": "shelf"}))])

    agent_mod._groq_complete = fake_complete
    agent_mod.Client = FakeClient
    try:
        res = asyncio.run(agent_mod.run_chat(
            "add stock", auth_token="tok", mcp_url="http://x/mcp/"))
    finally:
        agent_mod._groq_complete = orig_complete
        agent_mod.Client = orig_client
    assert res["pending_action"]["tool"] == "adjust_stock"
    assert res["pending_action"]["delta"] == 2
    assert res["pending_action"]["preview_token"] == "pt"


def test_pg_stock_concurrency():
    """Two same-token concurrent executes: exactly one wins (PostgreSQL).

    Skipped with an explicit reason when PostgreSQL is unavailable.
    """
    import socket
    import threading
    from urllib.parse import urlparse

    from app.core.security import hash_password as _hash
    from app.models.user import User as _User

    db_url = settings.DATABASE_URL
    try:
        parts = urlparse(db_url)
        socket.create_connection((parts.hostname, parts.port or 5432), timeout=3).close()
    except OSError:
        pytest.skip("PostgreSQL unreachable at DATABASE_URL; concurrency unverified")
    if "+aiosqlite" in db_url or db_url.startswith("sqlite"):
        pytest.skip("DATABASE_URL is sqlite; row-lock concurrency unverified")

    from sqlalchemy import create_engine as _create_engine

    pg_engine = _create_engine(db_url)
    try:
        with Session(pg_engine) as probe:
            probe.exec(select(Product)).first()
    except Exception:
        pytest.skip("PostgreSQL schema unavailable; concurrency unverified")

    import app.mcp.auth as _auth
    import app.mcp.guards as _guards
    import app.mcp.tools.inventory as _inv

    suffix = uuid4().hex[:8]
    orig = (_auth.engine, _guards.engine, _inv.engine)
    _auth.engine = _guards.engine = _inv.engine = pg_engine
    created = {}

    def mint(email):
        from app.core.security import create_access_token as _tok

        with Session(pg_engine) as s:
            u = s.exec(select(_User).where(_User.email == email)).first()
            return _tok(subject=u.email, role=u.role.value, audience="admin",
                        token_version=u.token_version), str(u.id)

    try:
        with Session(pg_engine) as s:
            mgr = _User(email=f"pgmgr-{suffix}@t.com", username=f"pgmgr-{suffix}",
                        password_hash=_hash("x"), role=UserRole.manager,
                        full_name="pg", is_active=True, email_verified=True)
            s.add(mgr)
            s.commit()
            s.refresh(mgr)
            # Scratch least-privilege role (dev PG predates the migration):
            # inventory.adjust grant only, removed in cleanup.
            perm = s.exec(select(Permission).where(
                Permission.key == "inventory.adjust")).first()
            if perm is None:
                perm = Permission(key="inventory.adjust", label="t", module="inventory",
                                  description="t")
                s.add(perm)
                s.commit()
                s.refresh(perm)
            role = Role(name=f"pg-{suffix}", slug=f"pg-{suffix}",
                        description="t", is_system=False)
            s.add(role)
            s.commit()
            s.refresh(role)
            s.add(RolePermissionLink(role_id=role.id, permission_id=perm.id))
            s.add(UserRoleLink(user_id=mgr.id, role_id=role.id))
            s.commit()
            prod = Product(name=f"PG Race {suffix}", slug=f"pg-race-{suffix}",
                           price=Decimal("10.00"))
            s.add(prod)
            s.commit()
            s.refresh(prod)
            var = ProductVariant(product_id=prod.id, sku=f"PG-SKU-{suffix}", stock=10)
            s.add(var)
            s.commit()
            created.update(product_id=str(prod.id), sku=var.sku, user_email=mgr.email)
        tok, _ = mint(created["user_email"])
        pre = asyncio.run(_inv.adjust_stock(created["sku"], 5, reason="race", token=tok))
        assert pre["success"] is True, pre
        barrier = threading.Barrier(2)
        outcomes = []

        def attempt():
            barrier.wait(timeout=10)
            outcomes.append(asyncio.run(_inv.adjust_stock(
                created["sku"], 5, reason="race",
                preview_token=pre["preview_token"], confirmed=True, token=tok)))

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        [t.start() for t in threads]
        [t.join(timeout=60) for t in threads]
        wins = [o for o in outcomes if o.get("success") is True]
        assert len(outcomes) == 2 and len(wins) == 1, outcomes
        with Session(pg_engine) as s:
            final = s.exec(
                select(ProductVariant).where(ProductVariant.sku == created["sku"])).first()
            assert int(final.stock) == 15, f"expected single +5 application, got {final.stock}"
    finally:
        _auth.engine, _guards.engine, _inv.engine = orig
        try:
            with Session(pg_engine) as s:
                from app.models.admin_audit import AdminAuditLog

                for row in s.exec(select(AdminAuditLog).where(
                        AdminAuditLog.actor_id.in_(
                            select(_User.id).where(
                                _User.email == created.get("user_email"))))).all():
                    s.delete(row)
                for row in s.exec(select(ProductVariant).where(
                        ProductVariant.sku == created.get("sku"))).all():
                    s.delete(row)
                for row in s.exec(select(Product).where(
                        Product.slug == f"pg-race-{suffix}")).all():
                    s.delete(row)
                for row in s.exec(select(_User).where(
                        _User.email == created.get("user_email"))).all():
                    for link in s.exec(select(UserRoleLink).where(
                            UserRoleLink.user_id == row.id)).all():
                        s.delete(link)
                    s.delete(row)
                for row in s.exec(select(Role).where(
                        Role.slug == f"pg-{suffix}")).all():
                    for link in s.exec(select(RolePermissionLink).where(
                            RolePermissionLink.role_id == row.id)).all():
                        s.delete(link)
                    s.delete(row)
                for row in s.exec(select(Permission).where(
                        Permission.key == "inventory.adjust")).all():
                    leftovers = s.exec(select(RolePermissionLink).where(
                        RolePermissionLink.permission_id == row.id)).all()
                    if not leftovers:
                        s.delete(row)
                s.commit()
        except Exception:
            pass
        pg_engine.dispose()
