"""STEP-1: MCP JWT authentication (no RBAC, no business logic).

Reuses the existing REST auth chain:
  app/core/security.py:decode_access_token
  app/repositories/user.py:get_user_by_email
  app/repositories/token.py:session_is_valid

Transport: token arrives either as an explicit tool arg (works with the
current high-level MCP Client which cannot set custom headers) or via the
HTTP Authorization header carried on ctx.headers (populated by the
streamable-HTTP transport). No new secret, lib, or user lookup.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import Session

from app.core.security import decode_access_token
from app.db.database import engine
from app.repositories.token import session_is_valid
from app.repositories.user import get_user_by_email


class MCPAuthError(Exception):
    """401-equivalent auth failure for MCP tools."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = 401

    def to_dict(self) -> dict[str, Any]:
        return {"success": False, "error": self.detail}


def extract_bearer_token(auth_header: str | None) -> str | None:
    """Parse 'Bearer <jwt>' (case-insensitive scheme, tolerant whitespace)."""
    if not auth_header:
        return None
    header = auth_header.strip()
    if not header:
        return None
    scheme, sep, value = header.partition(" ")
    if not sep:
        # No scheme separator: bare token, unless it is a lone scheme word.
        if header.lower() == "bearer":
            return None
        return header
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    return token or None


def get_token_from_context(ctx: Any | None) -> str | None:
    """Read Authorization header from MCP Context (HTTP transport only)."""
    if ctx is None:
        return None
    try:
        headers = ctx.headers
    except Exception:
        return None
    if not headers:
        return None
    # Headers may be case-variant; normalize lookup.
    for key in ("authorization", "Authorization", "AUTHORIZATION"):
        if key in headers:
            return extract_bearer_token(headers[key])
    # Fallback: case-insensitive scan.
    try:
        items = headers.items()  # type: ignore[union-attr]
    except Exception:
        return None
    for k, v in items:
        if str(k).lower() == "authorization":
            return extract_bearer_token(str(v))
    return None


def resolve_user_from_token(token: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate JWT and return (user_info, payload).

    Opens a short-lived sync Session (same engine as REST). Returns
    detached primitives only — never the ORM object — so callers are safe
    after the session closes.
    """
    if not token:
        raise MCPAuthError("Missing credentials")

    payload = decode_access_token(token)
    if payload is None:
        raise MCPAuthError("Could not validate credentials")

    email = payload.get("sub")
    if not email:
        raise MCPAuthError("Could not validate credentials")

    with Session(engine) as session:
        user = get_user_by_email(session, email)
        if user is None or not user.is_active:
            raise MCPAuthError("Could not validate credentials")
        if not session_is_valid(session, user, payload):
            raise MCPAuthError("Could not validate credentials")

        role = getattr(user.role, "value", user.role)
        user_info = {
            "id": str(user.id),
            "email": user.email,
            "role": str(role) if role is not None else None,
            "is_active": bool(user.is_active),
        }
        # Copy payload to plain dict (jose returns dict already).
        payload_copy = dict(payload)

    return user_info, payload_copy


def require_mcp_user(ctx: Any | None = None, token: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """STEP-1 entry point for tools: explicit token arg wins, else ctx header.

    Usage from a tool:
        user, payload = require_mcp_user(ctx, token)
    Raises MCPAuthError on failure; callers convert to error dict.
    """
    candidate = (token or "").strip() or None
    if candidate is not None and candidate.lower().startswith("bearer "):
        candidate = extract_bearer_token(candidate)
    if candidate is None:
        candidate = get_token_from_context(ctx)
    return resolve_user_from_token(candidate)


def parse_user_id(user_info: dict[str, Any]) -> UUID | None:
    try:
        return UUID(str(user_info.get("id")))
    except Exception:
        return None
