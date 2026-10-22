"""STEP-2: MCP RBAC guard reusing the existing REST permission system.

Reuses (no fork):
  app/api/deps.py:_assert_admin_audience  (aud must be admin)
  app/repositories/rbac.py:user_has_permission (DB union across user_roles)
  app/core/rbac_catalog.py: PERMISSIONS key "orders.view"

Identity comes from STEP-1:
  app/mcp/auth.py:require_mcp_user -> (user_info, payload)

No PostgreSQL business data touched here — only the RBAC link tables that
the REST admin API already reads. No destructive permissions granted.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session

from app.api.deps import _assert_admin_audience
from app.db.database import engine
from app.mcp.auth import MCPAuthError, parse_user_id, require_mcp_user
from app.repositories.rbac import user_has_permission

# Read-only permission for STEP-2/3. Defined in app/core/rbac_catalog.py:28
# ("orders.view", "View orders", "orders", ...). Staff+Manager+Admin hold it
# via SYSTEM_ROLES; customer holds nothing.
ORDERS_VIEW = "orders.view"

# Write permission gating the MCP cancel_order tool. Mirrors
# app/api/v1/admin/refunds.py:admin_cancel_order (require_perm("orders.update")).
ORDERS_UPDATE = "orders.update"

# Money permission gating the MCP issue_refund tool. Mirrors
# app/api/v1/admin/refunds.py:refund_cancelled_order (require_perm("orders.refund")).
ORDERS_REFUND = "orders.refund"

# Product/inventory permissions gating the MCP product tools. The agent
# mirrors the UI keys: stock and prices are edited through the product
# endpoints (products.update), so the stock/price tools accept that key
# OR the narrower specialist key (inventory.adjust / manage_prices).
PRODUCTS_VIEW = "products.view"
PRODUCTS_UPDATE = "products.update"
PRODUCTS_DELETE = "products.delete"
PRODUCTS_MANAGE_PRICES = "products.manage_prices"
INVENTORY_ADJUST = "inventory.adjust"

# Analytics reads. Mirrors the REST report routes in
# app/api/v1/analytics.py (all gated on reports.view).
REPORTS_VIEW = "reports.view"

# Payment inspection reads. The catalog reserves payments.view for payment
# inspection endpoints; refund inspection mirrors the admin refund routes.
PAYMENTS_VIEW = "payments.view"


class MCPForbiddenError(Exception):
    """403-equivalent permission failure for MCP tools."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = 403

    def to_dict(self) -> dict[str, Any]:
        return {"success": False, "error": self.detail}


def require_mcp_perm(
    ctx: Any | None = None,
    token: str | None = None,
    permission: str = ORDERS_VIEW,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authenticate (STEP-1) then enforce admin audience + RBAC permission.

    Raises MCPAuthError (401) or MCPForbiddenError (403). Callers convert
    to error dicts so the MCP transport stays JSON.
    """
    user_info, payload = require_mcp_user(ctx, token)

    # Same audience gate as REST require_perm/require_role: storefront
    # sessions can never reach admin tools, even with the right grants.
    try:
        _assert_admin_audience(payload)
    except HTTPException as exc:
        raise MCPForbiddenError(str(exc.detail or "Insufficient permissions"))

    user_id = parse_user_id(user_info)
    if user_id is None:
        raise MCPAuthError("Could not validate credentials")

    with Session(engine) as session:
        allowed = user_has_permission(session, user_id, permission)

    if not allowed:
        raise MCPForbiddenError("Insufficient permissions")

    return user_info, payload


def require_mcp_perm_any(
    ctx: Any | None = None,
    token: str | None = None,
    *permissions: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Same as require_mcp_perm but passes when the user holds ANY key.

    Used where the agent must mirror the UI: e.g. stock lives on the
    variant edited via products.update, so adjust_stock accepts
    products.update OR inventory.adjust. Revoking every listed key still
    blocks both paths together.
    """
    user_info, payload = require_mcp_user(ctx, token)

    try:
        _assert_admin_audience(payload)
    except HTTPException as exc:
        raise MCPForbiddenError(str(exc.detail or "Insufficient permissions"))

    user_id = parse_user_id(user_info)
    if user_id is None:
        raise MCPAuthError("Could not validate credentials")

    with Session(engine) as session:
        allowed = any(
            user_has_permission(session, user_id, permission)
            for permission in permissions
        )

    if not allowed:
        raise MCPForbiddenError("Insufficient permissions")

    return user_info, payload
