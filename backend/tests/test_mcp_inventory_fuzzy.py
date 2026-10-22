# tests/test_mcp_inventory_fuzzy.py
"""MCP check_stock fuzzy resolution (isolated sqlite DB).

Guards the "iPhone Blue Titanium" failure: the stock path resolved only
exact SKU/UUID/slug, so natural-language variant queries returned
"not found" (or a guessed refusal) while the row existed. check_stock
must now resolve exact identifiers directly AND fall back to a bounded
product/variant word match.
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
from app.models.product import Product, ProductVariant  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402

import app.mcp.auth as mcp_auth  # noqa: E402
import app.mcp.guards as mcp_guards  # noqa: E402
import app.mcp.tools.inventory as mcp_inventory  # noqa: E402

TEST_DB = "/tmp/mcp_inventory_fuzzy_test.db"
PASSWORD = "TestPass123"


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

    originals = (mcp_auth.engine, mcp_guards.engine, mcp_inventory.engine)
    mcp_auth.engine = test_engine
    mcp_guards.engine = test_engine
    mcp_inventory.engine = test_engine

    with TestingSession() as s:
        _seed_rbac(s)
        staff = _make_user(s, "staffer@fuzzy-test.com", UserRole.staff)
        customer = _make_user(s, "shopper@fuzzy-test.com", UserRole.customer)
        product = Product(
            name="iPhone 15 Pro Max",
            slug="iphone-15-pro-max",
            price=Decimal("159900.00"),
        )
        s.add(product)
        s.commit()
        s.refresh(product)
        for sku, color, storage, stock in (
            ("IP15PM-256-NAT", "Natural Titanium", "256GB", 25),
            ("IP15PM-512-NAT", "Natural Titanium", "512GB", 14),
            ("IP15PM-256-BLU", "Blue Titanium", "256GB", 20),
        ):
            s.add(
                ProductVariant(
                    product_id=product.id,
                    sku=sku,
                    attributes={"color": color, "storage": storage},
                    stock=stock,
                )
            )
        s.commit()

    def token_for(user, audience="admin"):
        return create_access_token(
            subject=user.email,
            role=user.role.value,
            audience=audience,
            token_version=user.token_version,
        )

    try:
        with TestingSession() as s2:
            staff2 = s2.exec(select(User).where(User.email == "staffer@fuzzy-test.com")).first()
            cust2 = s2.exec(select(User).where(User.email == "shopper@fuzzy-test.com")).first()
            yield {"staff": token_for(staff2), "customer": token_for(cust2)}
    finally:
        mcp_auth.engine, mcp_guards.engine, mcp_inventory.engine = originals


def run(coro):
    return asyncio.run(coro)


def test_exact_sku_unchanged(env):
    from app.core.region import currency_code

    res = run(mcp_inventory.check_stock("IP15PM-256-BLU", token=env["staff"]))
    assert res["success"] is True
    assert res["variant"]["sku"] == "IP15PM-256-BLU"
    assert res["variant"]["stock"] == 20
    assert "match" not in res  # exact path shape untouched
    assert res["currency"] == currency_code()


def test_exact_slug_unchanged(env):
    res = run(mcp_inventory.check_stock("iphone-15-pro-max", token=env["staff"]))
    assert res["success"] is True
    assert res["product_name"] == "iPhone 15 Pro Max"
    assert res["total_stock"] == 25 + 14 + 20


def test_fuzzy_words_resolve_single_variant(env):
    res = run(mcp_inventory.check_stock("iphone blue titanium", token=env["staff"]))
    assert res["success"] is True
    assert res["variant"]["sku"] == "IP15PM-256-BLU"
    assert res["variant"]["stock"] == 20
    assert res["match"] == "fuzzy"
    assert res["product_name"] == "iPhone 15 Pro Max"


def test_fuzzy_partial_words(env):
    res = run(mcp_inventory.check_stock("blue titanium", token=env["staff"]))
    assert res["success"] is True
    assert res["variant"]["sku"] == "IP15PM-256-BLU"
    assert res["match"] == "fuzzy"


def test_fuzzy_ambiguous_returns_candidates(env):
    res = run(mcp_inventory.check_stock("titanium", token=env["staff"]))
    assert res["success"] is True
    assert res["match"] == "ambiguous"
    assert len(res["variants"]) == 3
    assert {v["sku"] for v in res["variants"]} == {
        "IP15PM-256-NAT",
        "IP15PM-512-NAT",
        "IP15PM-256-BLU",
    }


def test_unknown_still_fails_with_hint(env):
    res = run(mcp_inventory.check_stock("zzzqqq-no-such-thing", token=env["staff"]))
    assert res["success"] is False
    assert "SKU" in res["error"]


def test_inventory_wraps_fuzzy(env):
    res = run(mcp_inventory.check_product_inventory("iphone blue titanium", token=env["staff"]))
    assert res["success"] is True
    assert res["availability"] == "in_stock"
    assert len(res["variants"]) == 1
    assert res["variants"][0]["sku"] == "IP15PM-256-BLU"


def test_customer_forbidden(env):
    res = run(mcp_inventory.check_stock("IP15PM-256-BLU", token=env["customer"]))
    assert res == {"success": False, "error": "Insufficient permissions"}


def test_invalid_jwt(env):
    res = run(mcp_inventory.check_stock("IP15PM-256-BLU", token="bad.jwt.here"))
    assert res["success"] is False
