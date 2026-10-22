# tests/test_admin_2fa.py
"""OTP step-up for privileged logins (isolated sqlite DB, fixed code 123456).

Flow under test:
  staff  -> POST /login -> {otp_required, challenge_token} (NO tokens)
        -> POST /login/verify-otp {challenge, 123456} -> TokenPair
  shopper -> POST /login -> TokenPair immediately (no challenge)
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
from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES

settings.ENVIRONMENT = "test"  # keep the APScheduler sweep out of tests

from app.api.deps import get_session  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.rbac import Permission, Role, RolePermissionLink  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.repositories import rbac as rbac_repo  # noqa: E402
from app.services import otp_service  # noqa: E402

TEST_DB = "/tmp/admin_2fa_test.db"
FIXED_CODE = "123456"

PASSWORD = "TestPass123"


def _seed(session: Session) -> None:
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
        for key in spec["permissions"]:
            session.add(
                RolePermissionLink(role_id=role.id, permission_id=perms[key].id)
            )
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
        _seed(s)
        _make_user(s, "staffer@2fa-test.com", UserRole.staff)
        _make_user(s, "shopper@2fa-test.com", UserRole.customer)

    # Deterministic code + no real email traffic (module-scoped fixture
    # cannot use the function-scoped `monkeypatch` fixture).
    code_patch = mock.patch.object(
        otp_service, "generate_otp", return_value=FIXED_CODE
    )
    mail_patch = mock.patch.object(
        otp_service.email_service, "send_email", return_value=True
    )
    code_patch.start()
    mail_patch.start()

    def override_session():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    # Fresh rate-limit buckets: the limiter is process-global (keyed by IP)
    # and other test modules share this process.
    limiter._storage.reset()
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        mail_patch.stop()
        code_patch.stop()


def _staff_challenge(client) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "staffer@2fa-test.com", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------- Challenge issuance ----------

def test_privileged_login_returns_challenge_not_tokens(client):
    body = _staff_challenge(client)
    assert body.get("otp_required") is True
    assert body.get("challenge_token")
    assert "access_token" not in body
    assert "refresh_token" not in body
    assert "@" in (body.get("email_masked") or "")
    assert "staffer" not in (body.get("email_masked") or "")


def test_customer_login_unaffected(client):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "shopper@2fa-test.com", "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert "otp_required" not in body


# ---------- Verify ----------

def test_verify_correct_code_issues_tokens(client):
    body = _staff_challenge(client)
    resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={
            "challenge_token": body["challenge_token"],
            "otp_code": FIXED_CODE,
        },
    )
    assert resp.status_code == 200, resp.text
    payload = jwt.decode(
        resp.json()["access_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        audience="admin",
    )
    assert payload["sub"] == "staffer@2fa-test.com"
    assert "products.view" in payload["permissions"]


def test_wrong_code_rejected_with_remaining_count(client):
    body = _staff_challenge(client)
    resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={
            "challenge_token": body["challenge_token"],
            "otp_code": "000000",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "attempt(s) remaining" in resp.json()["detail"]


def test_code_burned_after_max_attempts(client):
    body = _staff_challenge(client)
    challenge = body["challenge_token"]
    for _ in range(5):
        resp = client.post(
            "/api/v1/auth/login/verify-otp",
            json={"challenge_token": challenge, "otp_code": "000000"},
        )
        assert resp.status_code == 400, resp.text
    # Even the right code is now dead — a fresh challenge is required.
    resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": challenge, "otp_code": FIXED_CODE},
    )
    assert resp.status_code == 400, resp.text
    assert "locked" in resp.json()["detail"]


def test_tampered_challenge_rejected(client):
    resp = client.post(
        "/api/v1/auth/login/verify-otp",
        json={"challenge_token": "tampered.token.here", "otp_code": FIXED_CODE},
    )
    assert resp.status_code == 401, resp.text


# ---------- Resend ----------

def test_resend_cooldown_enforced(client):
    body = _staff_challenge(client)
    resp = client.post(
        "/api/v1/auth/login/resend-otp",
        json={"challenge_token": body["challenge_token"]},
    )
    # A code was just issued during login -> cooldown must bite.
    assert resp.status_code == 429, resp.text
