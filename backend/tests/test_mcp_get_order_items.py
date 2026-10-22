# tests/test_mcp_get_order_items.py
"""MCP get_order line-item regression (isolated sqlite DB).

Guards the ORD-20261012102247 hallucination: get_order used to return only
item_count + grand_total, so follow-up "what is the product?" guessed from
price proximity. It must now return items[] snapshots verbatim.
"""
import asyncio
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from app.core.config import settings

settings.ENVIRONMENT = "test"

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.models.order import Order, OrderItem, OrderStatus  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.orders as mcp_orders  # noqa: E402
from app.mcp import agent as mcp_agent  # noqa: E402

TEST_DB = "/tmp/mcp_get_order_items_test.db"
PASSWORD = "TestPass123"

EXPECTED_ITEM_FIELDS = {
    "product_name",
    "variant_sku",
    "variant_attributes",
    "quantity",
    "unit_price",
    "line_total",
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
        staff = _make_user(s, "staffer@items-test.com", UserRole.staff)
        customer = _make_user(s, "shopper@items-test.com", UserRole.customer)
        order = Order(
            order_number="ORD-ITEM-001",
            user_id=customer.id,
            shipping_address_id=uuid4(),
            billing_address_id=uuid4(),
            subtotal=Decimal("200.00"),
            grand_total=Decimal("200.00"),
            status=OrderStatus.DELIVERED,
            payment_status="paid",
        )
        s.add(order)
        s.commit()
        s.refresh(order)
        s.add(
            OrderItem(
                order_id=order.id,
                variant_id=uuid4(),
                product_name="Real Product Alpha",
                variant_sku="ALPHA-M",
                variant_attributes={"size": "M"},
                quantity=1,
                unit_price=Decimal("150.00"),
                line_total=Decimal("150.00"),
            )
        )
        s.add(
            OrderItem(
                order_id=order.id,
                variant_id=uuid4(),
                product_name="Real Product Beta",
                variant_sku="BETA-S",
                variant_attributes={"size": "S"},
                quantity=1,
                unit_price=Decimal("50.00"),
                line_total=Decimal("50.00"),
            )
        )
        empty = Order(
            order_number="ORD-EMPTY-001",
            user_id=customer.id,
            shipping_address_id=uuid4(),
            billing_address_id=uuid4(),
            subtotal=Decimal("0.00"),
            grand_total=Decimal("0.00"),
            status=OrderStatus.PENDING,
            payment_status="pending",
        )
        s.add(empty)
        s.commit()
        order_id = str(order.id)

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email,
            role=user.role.value,
            audience=audience,
            token_version=user.token_version,
        )

    try:
        with TestingSession() as s2:
            staff2 = s2.exec(select(User).where(User.email == "staffer@items-test.com")).first()
            yield {"staff": token_for(staff2), "order_id": order_id}
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_orders.engine = originals


def run(coro):
    return asyncio.run(coro)


def test_get_order_returns_items_verbatim(env):
    res = run(mcp_orders.get_order(env["order_id"], token=env["staff"]))
    assert res["success"] is True
    order = res["order"]
    assert order["item_count"] == 2
    assert isinstance(order["items"], list) and len(order["items"]) == 2
    names = {i["product_name"] for i in order["items"]}
    assert names == {"Real Product Alpha", "Real Product Beta"}
    for item in order["items"]:
        assert set(item.keys()) == EXPECTED_ITEM_FIELDS
    alpha = next(i for i in order["items"] if i["variant_sku"] == "ALPHA-M")
    assert alpha["quantity"] == 1
    assert float(alpha["unit_price"]) == 150.00
    assert float(alpha["line_total"]) == 150.00
    blob = str(order["items"])
    assert "Sony" not in blob  # no catalog guess may appear
    assert "snapshot" not in blob.lower()


def test_get_order_by_number_returns_same_items(env):
    res = run(mcp_orders.get_order("ORD-ITEM-001", token=env["staff"]))
    assert res["success"] is True
    assert len(res["order"]["items"]) == 2


def test_get_order_empty_items(env):
    res = run(mcp_orders.get_order("ORD-EMPTY-001", token=env["staff"]))
    assert res["success"] is True
    assert res["order"]["items"] == []
    assert res["order"]["item_count"] == 0


def test_list_orders_stays_summary_only(env):
    res = run(mcp_orders.list_orders(limit=5, token=env["staff"]))
    assert res["success"] is True
    for row in res["orders"]:
        assert "items" not in row  # list stays light; detail via get_order


def test_agent_guidance_forbids_price_guessing():
    assert "items[]" in mcp_agent.ORDER_ITEMS_GUIDANCE
    assert "get_order" in mcp_agent.ORDER_ITEMS_GUIDANCE
    assert "grand_total" in mcp_agent.ORDER_ITEMS_GUIDANCE
    assert "Never guess a product" in mcp_agent.AGENT_SYSTEM_PROMPT
