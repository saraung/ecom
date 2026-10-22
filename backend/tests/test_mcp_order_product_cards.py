# tests/test_mcp_order_product_cards.py
"""MCP get_order product cards (isolated sqlite DB).

get_order used to expose only line-item snapshots (no product id/slug/image),
so the chat UI could not render a product card when the answer came from an
order context ("what's the product?"). It now also returns product_cards,
resolved variant -> product -> slug + first image (same resolution as the
admin order detail), which the agent collects into the chat response.
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
from app.models.product import Product, ProductVariant  # noqa: E402
from app.models.product_image import ProductImage  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.orders as mcp_orders  # noqa: E402
from app.mcp.agent import _card_candidates, collect_product_cards, MAX_PRODUCT_CARDS  # noqa: E402

TEST_DB = "/tmp/mcp_order_product_cards_test.db"
PASSWORD = "TestPass123"
PRODUCT_ID = None
CARD_ORDER_ID = None
BARE_ORDER_ID = None


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
    global PRODUCT_ID, CARD_ORDER_ID, BARE_ORDER_ID
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
        staff = _make_user(s, "staffer@cards-test.com", UserRole.staff)
        customer = _make_user(s, "shopper@cards-test.com", UserRole.customer)

        product = Product(
            name="Nike Air Max 270 Running Shoes",
            slug="nike-air-max-270-running-shoes",
            price=Decimal("12995.00"),
        )
        s.add(product)
        s.commit()
        s.refresh(product)
        PRODUCT_ID = str(product.id)

        variant = ProductVariant(
            product_id=product.id,
            sku="NIKE-AM270-RED-9",
            attributes={"size": "9", "color": "Red"},
            stock=4,
        )
        s.add(variant)
        s.commit()
        s.refresh(variant)

        # First image must be the LOWEST sort_order.
        s.add(ProductImage(product_id=product.id, url="https://cdn/back.jpg", sort_order=5))
        s.add(ProductImage(product_id=product.id, url="https://cdn/hero.jpg", sort_order=0))

        order = Order(
            order_number="ORD-CARDS-001",
            user_id=customer.id,
            shipping_address_id=uuid4(),
            billing_address_id=uuid4(),
            subtotal=Decimal("12995.00"),
            grand_total=Decimal("12995.00"),
            status=OrderStatus.CONFIRMED,
            payment_status="paid",
        )
        s.add(order)
        s.commit()
        s.refresh(order)
        CARD_ORDER_ID = str(order.id)
        s.add(
            OrderItem(
                order_id=order.id,
                variant_id=variant.id,
                product_name="Nike Air Max 270 Running Shoes",
                variant_sku="NIKE-AM270-RED-9",
                variant_attributes={"size": "9"},
                quantity=1,
                unit_price=Decimal("12995.00"),
                line_total=Decimal("12995.00"),
            )
        )
        # Line whose variant no longer exists in the catalog: no card.
        s.add(
            OrderItem(
                order_id=order.id,
                variant_id=uuid4(),
                product_name="Deleted Product",
                variant_sku="GONE-SKU",
                variant_attributes={},
                quantity=1,
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
            )
        )
        s.commit()

        # Bare order: no resolvable catalog rows.
        bare = Order(
            order_number="ORD-BARE-001",
            user_id=customer.id,
            shipping_address_id=uuid4(),
            billing_address_id=uuid4(),
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            status=OrderStatus.PENDING,
            payment_status="pending",
        )
        s.add(bare)
        s.commit()
        s.refresh(bare)
        BARE_ORDER_ID = str(bare.id)
        s.add(
            OrderItem(
                order_id=bare.id,
                variant_id=uuid4(),
                product_name="Ghost Product",
                variant_sku="GHOST-1",
                variant_attributes={},
                quantity=1,
                unit_price=Decimal("100.00"),
                line_total=Decimal("100.00"),
            )
        )
        s.commit()

    with TestingSession() as s2:
        staff2 = s2.exec(select(User).where(User.email == "staffer@cards-test.com")).first()
        token = create_access_token(
            subject=staff2.email,
            role=staff2.role.value,
            audience="admin",
            token_version=staff2.token_version,
        )

    try:
        yield {"staff": token}
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_orders.engine = originals


def run(coro):
    return asyncio.run(coro)


def test_get_order_attaches_cards_from_catalog(env):
    res = run(mcp_orders.get_order("ORD-CARDS-001", token=env["staff"]))
    assert res["success"] is True
    cards = res.get("product_cards")
    assert isinstance(cards, list) and len(cards) == 1
    card = cards[0]
    assert card["id"] == PRODUCT_ID
    assert card["name"] == "Nike Air Max 270 Running Shoes"
    assert card["slug"] == "nike-air-max-270-running-shoes"
    assert card["image_url"] == "https://cdn/hero.jpg"  # lowest sort_order
    assert float(card["price"]) == 12995.00
    # Units in an order are not live stock: never mislabel.
    assert card["stock"] is None


def test_items_whitelist_unchanged(env):
    res = run(mcp_orders.get_order("ORD-CARDS-001", token=env["staff"]))
    for item in res["order"]["items"]:
        assert "image_url" not in item
        assert "product_id" not in item


def test_get_order_without_catalog_omits_cards(env):
    res = run(mcp_orders.get_order("ORD-BARE-001", token=env["staff"]))
    assert res["success"] is True
    assert "product_cards" not in res


def test_agent_collects_get_order_cards():
    result = {
        "success": True,
        "product_cards": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": "Demo",
                "slug": "demo",
                "price": 2499.0,
                "image_url": "https://example.com/i.png",
                "stock": None,
            }
        ],
    }
    pairs = _card_candidates("get_order", result)
    assert len(pairs) == 1
    cards, seen = [], set()
    collect_product_cards("get_order", result, cards, seen)
    assert len(cards) == 1 and cards[0]["slug"] == "demo"


def test_agent_collect_caps_get_order_cards():
    result = {
        "success": True,
        "product_cards": [
            {"id": f"id-{i}", "name": f"P{i}", "slug": f"p{i}"} for i in range(9)
        ],
    }
    cards, seen = [], set()
    collect_product_cards("get_order", result, cards, seen)
    assert len(cards) == MAX_PRODUCT_CARDS


def test_agent_ignores_get_order_without_cards():
    assert _card_candidates("get_order", {"success": True}) == []
