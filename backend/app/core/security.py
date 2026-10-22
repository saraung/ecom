from datetime import datetime, timedelta, timezone
from typing import Any
import uuid
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# Token audiences. A storefront token is a strictly weaker credential: it can
# only reach customer-scoped endpoints. ``require_perm`` (app/api/deps.py)
# rejects anything that is not AUDIENCE_ADMIN, so a session started in the shop
# can never be replayed against the admin API — not even after a refresh.
AUDIENCE_ADMIN = "admin"
AUDIENCE_STOREFRONT = "storefront"


def create_access_token(
    subject: str,
    role: str,
    permissions: list[str] | None = None,
    audience: str = AUDIENCE_ADMIN,
    session_id: str | None = None,
    token_version: int = 0,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "role": role,
        "permissions": permissions or [],
        "exp": expire,
        "type": "access",
        "aud": audience,
        "ver": token_version,
    }
    if session_id is not None:
        payload["sid"] = session_id
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# OTP step-up for privileged logins: the challenge token proves "password OK,
# OTP pending". Short-lived, single-purpose — it can only be exchanged at
# POST /auth/login/verify-otp, never used as an API credential.
CHALLENGE_TOKEN_EXPIRE_MINUTES = 5


def create_login_challenge(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=CHALLENGE_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire, "type": "challenge"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_login_challenge(token: str) -> str | None:
    """Return the challenged email, or None if invalid/expired/wrong type."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "challenge":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_refresh_token_value() -> str:
    # Opaque random string — NOT a JWT. Stored + hashed in DB, so it can be
    # revoked server-side (a self-contained JWT refresh token can't be revoked
    # without a blocklist, which is just this table anyway).
    return uuid.uuid4().hex + uuid.uuid4().hex


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            # We issue an "aud" claim (AUDIENCE_ADMIN / AUDIENCE_STOREFRONT) and
            # enforce it ourselves in app/api/deps.py::_assert_admin_audience.
            # python-jose would otherwise reject every token here, since it can
            # only validate "aud" against one expected audience and this codebase
            # accepts tokens from two different channels.
            options={"verify_aud": False},
        )
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


# ========== Password Reset Token Functions ==========

def generate_reset_token() -> str:
    """
    Generate a secure random token for password reset.
    Uses secrets.token_urlsafe for cryptographically secure random tokens.
    Returns a 32-byte (256-bit) URL-safe token.
    """
    return secrets.token_urlsafe(32)


def create_reset_jwt_token(email: str) -> str:
    """
    Create JWT token for password reset.
    Alternative to random token if you prefer JWT-based tokens.
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.RESET_TOKEN_EXPIRE_HOURS)
    payload = {"sub": email, "exp": expire, "type": "reset"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_reset_jwt_token(token: str) -> str | None:
    """
    Verify JWT reset token and return email.
    Returns email if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def verify_reset_token(token: str) -> dict[str, Any] | None:
    """
    Verify a reset token (JWT-based).
    Returns user data if valid, None otherwise.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return {"email": payload.get("sub")}
    except JWTError:
        return None
