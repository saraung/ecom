"""STEP-2 probe tool: proves User -> RBAC inside MCP (read-only, no PG orders)."""

from __future__ import annotations

from typing import Any

from app.mcp.auth import MCPAuthError
from app.mcp.guards import MCPForbiddenError, ORDERS_VIEW, require_mcp_perm

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


async def check_orders_view(ctx: Context | None = None, token: str | None = None) -> dict:
    """Check whether the caller holds the existing `orders.view` permission.

    Flow: STEP-1 JWT -> User, then admin-audience gate + DB RBAC lookup.
    No order data read, no writes. Destructive permissions never checked here.
    """
    try:
        user, payload = require_mcp_perm(ctx, token, ORDERS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()
    return {
        "success": True,
        "allowed": True,
        "permission": ORDERS_VIEW,
        "user": user,
        "audience": payload.get("aud"),
    }
