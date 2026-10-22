# tests/test_rbac.py
"""Dynamic single-tenant RBAC: catalog, guards, role CRUD, assignment.

Isolated: runs against a throwaway sqlite DB via dependency_overrides —
never touches the dev postgres.
"""
import os
from unittest import mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, select, SQLModel

from app.core.config import settings
from app.core.rbac_catalog import PERMISSIONS, PERMISSION_KEYS, SYSTEM_ROLES

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from app.api.deps import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.database import engine as _prod_engine  # noqa: E402  (unused, ensures package init)
from app.main import app  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.rbac import Permission, Role  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402
from app.services import otp_service  # noqa: E402

TEST_DB = "/tmp/rbac_test.db"

_admin_headers: dict = {}
_packer_headers: dict = {}
_customer_id: str = ""


def _seed_catalog(session: Session) -> None:
    for key, label, module, description in PERMISSIONS:
        session.add(
            Permission(
                key=key, label=label, module=module, description=description
            )
        )
    session.flush()
    perms = {p.key: p for p in session.exec(select(Permission)).all()}
    for slug, spec in SYSTEM_ROLES.items():
        role = Role(
            name=spec["name"],
            slug=slug,
            description=spec["description"],
            is_system=True,
        )
        session.add(role)
        session.flush()
        from app.models.rbac import RolePermissionLink

        for key in spec["permissions"]:
            session.add(
                RolePermissionLink(role_id=role.id, permission_id=perms[key].id)
            )
    session.commit()


def _make_user(session: Session, email: str, legacy: UserRole) -> User:
    user = User(
        email=email,
        username=f"u_{uuid4().hex[:8]}",
        password_hash=hash_password("TestPass123"),
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
    return user


@pytest.fixture(scope="module")
def client():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    test_engine = create_engine(f"sqlite:///{TEST_DB}")
    SQLModel.metadata.create_all(test_engine)
    TestingSession = sessionmaker(
        bind=test_engine, class_=Session, expire_on_commit=False
    )
    with TestingSession() as s:
        _seed_catalog(s)
        admin = _make_user(s, "admin@rbac-test.com", UserRole.admin)
        packer_user = _make_user(s, "packer@rbac-test.com", UserRole.customer)
        packer_role = rbac_repo.create_role(
            s,
            name="Packer",
            slug="packer",
            description="Can only view orders",
            permission_keys=["orders.view"],
            created_by=admin.id,
        )
        rbac_repo.set_user_roles(s, packer_user, [packer_role])
        global _customer_id
        _customer_id = str(
            _make_user(s, "shopper@rbac-test.com", UserRole.customer).id
        )

    def override_session():
        with TestingSession() as session:
            yield session

    # Privileged logins now stop at the OTP challenge — complete it with a
    # deterministic code and a stubbed mailer (no real email traffic).
    code_patch = mock.patch.object(
        otp_service, "generate_otp", return_value="123456"
    )
    mail_patch = mock.patch.object(
        otp_service.email_service, "send_email", return_value=True
    )
    code_patch.start()
    mail_patch.start()

    def _login(c, email: str) -> str:
        resp = c.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "TestPass123"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body.get("otp_required"):
            verify = c.post(
                "/api/v1/auth/login/verify-otp",
                json={
                    "challenge_token": body["challenge_token"],
                    "otp_code": "123456",
                },
            )
            assert verify.status_code == 200, verify.text
            body = verify.json()
        return f"Bearer {body['access_token']}"

    app.dependency_overrides[get_session] = override_session
    # Fresh rate-limit buckets: the limiter is process-global (keyed by IP)
    # and other test modules share this process.
    limiter._storage.reset()
    try:
        with TestClient(app) as c:
            # Log in both users once for the whole module.
            _admin_headers["Authorization"] = _login(c, "admin@rbac-test.com")
            _packer_headers["Authorization"] = _login(c, "packer@rbac-test.com")
            yield c
    finally:
        app.dependency_overrides.clear()
        mail_patch.stop()
        code_patch.stop()


# ---------- Catalog sanity ----------

def test_catalog_covers_all_guard_permissions():
    # Every permission key referenced by the codebase must exist in the seed.
    assert "products.delete" in PERMISSION_KEYS
    assert "roles.manage" in PERMISSION_KEYS
    assert "users.manage_roles" in PERMISSION_KEYS
    assert len(PERMISSION_KEYS) == len(set(PERMISSION_KEYS))
    import ast
    from pathlib import Path
    referenced = set()
    for path in (Path(__file__).resolve().parents[1] / "app").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require_perm":
                referenced.update(arg.value for arg in node.args
                                  if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    assert referenced <= set(PERMISSION_KEYS), referenced - set(PERMISSION_KEYS)


def test_system_role_hierarchy_preserved():
    assert set(SYSTEM_ROLES["admin"]["permissions"]) == set(PERMISSION_KEYS)
    assert "roles.manage" not in SYSTEM_ROLES["manager"]["permissions"]
    assert "settings.manage" not in SYSTEM_ROLES["manager"]["permissions"]
    assert "products.delete" not in SYSTEM_ROLES["manager"]["permissions"]
    assert "dashboard.view" not in SYSTEM_ROLES["staff"]["permissions"]
    assert SYSTEM_ROLES["customer"]["permissions"] == []
    # But staff keeps day-to-day catalog access + order visibility.
    assert "products.create" in SYSTEM_ROLES["staff"]["permissions"]
    assert "orders.view" in SYSTEM_ROLES["staff"]["permissions"]


# ---------- Tokens + /me ----------

def test_login_token_carries_permissions(client):
    token = _admin_headers["Authorization"].split(" ", 1)[1]
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience="admin",
    )
    assert payload["role"] == "admin"
    assert "roles.manage" in payload["permissions"]
    assert "orders.view" in payload["permissions"]


def test_me_returns_roles_and_permissions(client):
    resp = client.get("/api/v1/auth/me", headers=_admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "admin" in body["roles"]
    assert "roles.manage" in body["permissions"]


# ---------- Custom-role enforcement ----------

def test_custom_role_can_view_but_not_update_orders(client):
    assert (
        client.get("/api/v1/admin/orders", headers=_packer_headers).status_code
        == 200
    )
    resp = client.put(
        f"/api/v1/admin/orders/{uuid4()}/status",
        json={"status": "confirmed"},
        headers=_packer_headers,
    )
    assert resp.status_code == 403, resp.text


def test_custom_role_cannot_manage_users(client):
    resp = client.get("/api/v1/admin/users", headers=_packer_headers)
    assert resp.status_code == 403, resp.text


def test_staff_direct_calls_to_cod_reconciliation_are_forbidden(client):
    """The API must enforce cod.view/cod.reconcile even if the UI is bypassed."""
    rid = uuid4()
    csv_file = ("cod.csv", b"awb,order_number\n", "text/csv")
    cases = [
        ("get", "/api/v1/admin/cod/summary", {}),
        ("get", "/api/v1/admin/cod/remittances", {}),
        ("get", f"/api/v1/admin/cod/remittances/{rid}", {}),
        ("get", f"/api/v1/admin/cod/remittances/{rid}/export", {}),
        ("post", f"/api/v1/admin/cod/remittances/{rid}/resolve", {
            "json": {"item_id": str(rid), "action": "exclude"},
        }),
        ("post", f"/api/v1/admin/cod/remittances/{rid}/confirm", {
            "json": {
                "utr": "UTR-STAFF",
                "bank_credit_amount": 1,
                "bank_credit_date": "2026-10-20",
            },
        }),
        ("post", f"/api/v1/admin/cod/remittances/{rid}/void", {}),
        ("post", "/api/v1/admin/cod/remittances", {
            "json": {
                "crf_id": "CRF-STAFF",
                "remittance_date": "2026-10-20",
                "items": [{"awb": "AWB-STAFF", "cod_amount": 1, "net_amount": 1}],
            },
        }),
        ("post", "/api/v1/admin/cod/remittances/simulate", {}),
        ("post", "/api/v1/admin/cod/collect-bulk", {
            "json": {"order_ids": [str(rid)]},
        }),
        ("post", "/api/v1/admin/cod/remittances/import/preview", {
            "files": {"file": csv_file},
        }),
        ("post", "/api/v1/admin/cod/remittances/import", {
            "files": {"file": csv_file},
            "data": {"crf_id": "CRF-STAFF", "remittance_date": "2026-10-20"},
        }),
    ]
    for method, path, kwargs in cases:
        resp = client.request(method, path, headers=_packer_headers, **kwargs)
        assert resp.status_code == 403, f"{method.upper()} {path}: {resp.text}"


# ---------- Role CRUD guards ----------

def test_role_crud_requires_roles_manage(client):
    # Packer is forbidden from even listing roles.
    assert (
        client.get("/api/v1/admin/roles", headers=_packer_headers).status_code
        == 403
    )
    # Unknown permission keys are rejected, not silently stored.
    resp = client.post(
        "/api/v1/admin/roles",
        json={"name": "Bogus", "permission_keys": ["orders.fly"]},
        headers=_admin_headers,
    )
    assert resp.status_code == 400, resp.text
    # Full lifecycle for a valid custom role.
    resp = client.post(
        "/api/v1/admin/roles",
        json={
            "name": "Support",
            "permission_keys": ["orders.view", "users.view"],
        },
        headers=_admin_headers,
    )
    assert resp.status_code == 201, resp.text
    role_id = resp.json()["id"]
    assert set(resp.json()["permissions"]) == {"orders.view", "users.view"}
    # System roles are protected from deletion.
    roles = client.get("/api/v1/admin/roles", headers=_admin_headers).json()
    admin_role = next(r for r in roles if r["slug"] == "admin")
    resp = client.delete(
        f"/api/v1/admin/roles/{admin_role['id']}", headers=_admin_headers
    )
    assert resp.status_code == 400, resp.text
    # Custom role deletes cleanly when unused.
    resp = client.delete(
        f"/api/v1/admin/roles/{role_id}", headers=_admin_headers
    )
    assert resp.status_code == 204, resp.text


def test_permission_catalog_is_read_only(client):
    perms = client.get(
        "/api/v1/admin/permissions", headers=_admin_headers
    ).json()
    assert {p["key"] for p in perms} == set(PERMISSION_KEYS)
    assert client.get(
        "/api/v1/admin/permissions", headers=_packer_headers
    ).status_code == 403


# ---------- Assignment (incl. legacy compat) ----------

def test_set_user_roles_and_self_lockout(client):
    # Assign two roles via the new endpoint.
    resp = client.put(
        f"/api/v1/admin/users/{_customer_id}/roles",
        json={"role_slugs": ["manager", "staff"]},
        headers=_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == {"manager", "staff"}
    # Unknown slug rejected.
    resp = client.put(
        f"/api/v1/admin/users/{_customer_id}/roles",
        json={"role_slugs": ["ghost"]},
        headers=_admin_headers,
    )
    assert resp.status_code == 400, resp.text
    # Admins cannot change their own roles (anti-lockout).
    admin_id = client.get("/api/v1/auth/me", headers=_admin_headers).json()["id"]
    resp = client.put(
        f"/api/v1/admin/users/{admin_id}/roles",
        json={"role_slugs": ["staff"]},
        headers=_admin_headers,
    )
    assert resp.status_code == 400, resp.text


def test_legacy_role_endpoint_still_works(client):
    resp = client.put(
        f"/api/v1/admin/users/{_customer_id}/role",
        json={"role": "staff"},
        headers=_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["staff"]


def _put_roles(client, slugs: list[str]) -> dict:
    """Assign role slugs and return the fresh AdminUserRead payload."""
    resp = client.put(
        f"/api/v1/admin/users/{_customer_id}/roles",
        json={"role_slugs": slugs},
        headers=_admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == set(slugs)
    read = client.get(
        f"/api/v1/admin/users/{_customer_id}", headers=_admin_headers
    ).json()
    assert set(read["roles"]) == set(slugs)
    return read


def test_legacy_role_picks_highest_not_first(client):
    """``users.role`` must not depend on the order roles were submitted.

    The legacy column is a single value older clients gate on (e.g. the
    Promotions page), and the roles UI appends newly-ticked roles in click
    order — so ticking ``customer`` first could otherwise downgrade a manager
    into a denied account.
    """
    # Read-only role submitted FIRST, privileged role last.
    read = _put_roles(client, ["customer", "manager"])
    assert read["role"] == "manager"

    # Reversing the submission order must NOT change the outcome.
    read = _put_roles(client, ["manager", "customer"])
    assert read["role"] == "manager"

    # Every system role at once, least-privileged first -> top one wins.
    read = _put_roles(client, ["customer", "staff", "manager", "admin"])
    assert read["role"] == "admin"

    # Same set submitted in the opposite order -> same answer.
    read = _put_roles(client, ["admin", "manager", "staff", "customer"])
    assert read["role"] == "admin"


def test_custom_only_role_set_leaves_legacy_role_alone(client):
    """With no legacy slug assigned, ``users.role`` keeps its previous value
    instead of being overwritten by a slug the enum cannot hold."""
    baseline = _put_roles(client, ["manager"])["role"]
    assert baseline == "manager"

    read = _put_roles(client, ["packer"])
    assert read["role"] == baseline  # unchanged, not clobbered

    # A custom role stacked under a legacy one still loses to the legacy one.
    read = _put_roles(client, ["packer", "staff"])
    assert read["role"] == "staff"
