"""STEP-1 probe tool: proves JWT -> User inside MCP (no RBAC, read-only)."""

from __future__ import annotations

from typing import Any

from app.mcp.auth import MCPAuthError, require_mcp_user

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


async def whoami(ctx: Context | None = None, token: str | None = None) -> dict:
    """Validate the caller's JWT and return identity (STEP-1 probe).

    Auth: explicit `token` arg preferred (current Client cannot set custom
    headers); falls back to HTTP `Authorization: Bearer <jwt>` on ctx.headers.
    No permission check here — STEP-2 adds `orders.view` etc.
    """
    try:
        user, payload = require_mcp_user(ctx, token)
    except MCPAuthError as exc:
        return exc.to_dict()
    return {
        "success": True,
        "authenticated": True,
        "user": user,
        "audience": payload.get("aud"),
        "token_version": payload.get("ver"),
    }
