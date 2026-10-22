from mcp.server.mcpserver import MCPServer

from app.mcp.tools.auth import whoami
from app.mcp.tools.permissions import check_orders_view
from app.mcp.tools.orders import get_order, list_orders, cancel_order, issue_refund
from app.mcp.tools.products import (
    list_products,
    get_product,
    compare_products,
    update_product,
    update_product_price,
    delete_product,
)
from app.mcp.tools.inventory import (
    check_stock,
    check_product_inventory,
    adjust_stock,
    list_low_stock_products,
)
from app.mcp.tools.analytics import (
    sales_summary,
    sales_trend,
    product_performance,
)
from app.mcp.tools.payments import (
    get_payment_status,
    list_refunds,
    list_payment_issues,
    get_refund_status,
)

mcp = MCPServer("Com Ecommerce MCP")

# NOTE on descriptions: the MCP framework defaults each tool's
# LLM-facing description to its full Python docstring, and that text is
# re-sent on EVERY agent turn (~16K chars measured). The six heaviest
# tools below carry explicit one-line descriptions instead — routing
# behavior (two-step previews, filters, no-date-filter) is preserved in
# compressed form, details stay in the docstrings for developers. Keep
# new descriptions short; tests/test_mcp_list_orders.py budgets the total.
# STEP-1 auth probe (JWT -> User, no RBAC).
mcp.tool()(whoami)
# STEP-2 permission probe (User -> RBAC orders.view, read-only, no PG orders).
mcp.tool()(check_orders_view)
# STEP-3 real tools (PostgreSQL, read-only).
mcp.tool(
    description=(
        "Get one order by UUID or order_number (read-only). Returns the "
        "summary plus item_count and items[] line snapshots (product_name, "
        "sku, quantity, prices) — quote verbatim, never infer."
    ),
)(get_order)
mcp.tool(
    description=(
        "List order summaries (read-only, paginated). Filter by status / "
        "payment_status / from_date / to_date (YYYY-MM-DD) with limit / "
        "offset. No product names — call get_order for line items."
    ),
)(list_orders)
mcp.tool(
    description=(
        "Preview then execute an order cancellation (two-step: call without "
        "confirmed for a preview, then with confirmed + preview_token). "
        "No money moves."
    ),
)(cancel_order)
mcp.tool(
    description=(
        "Preview then execute a refund (two-step: call without confirmed "
        "for a preview, then with confirmed + preview_token). Money moves "
        "only on execution."
    ),
)(issue_refund)
# Product catalog (reads) + confirmed product writes (preview first).
mcp.tool()(list_products)
mcp.tool()(get_product)
mcp.tool()(compare_products)
mcp.tool()(update_product)
mcp.tool()(update_product_price)
mcp.tool()(delete_product)
# Inventory reads + confirmed stock adjustments (preview first).
mcp.tool()(check_stock)
mcp.tool()(check_product_inventory)
mcp.tool(
    description=(
        "Preview then apply a signed stock delta to one variant (two-step: "
        "call without confirmed for a preview, then with confirmed + "
        "preview_token)."
    ),
)(adjust_stock)
mcp.tool(
    description=(
        "Variants at or below threshold stock (DB filter/paginate). Use for "
        "all low/out-of-stock questions."
    ),
)(list_low_stock_products)
# Sales & analytics (PostgreSQL aggregation, read-only).
mcp.tool(
    description=(
        "Revenue, orders, AOV plus status/payment/refund breakdowns over a "
        "period, with optional comparison. Use explicit from_date/to_date "
        "for month questions."
    ),
)(sales_summary)
mcp.tool()(sales_trend)
mcp.tool(
    description=(
        "Product rankings by view (top_units, top_revenue, by_category, "
        "slow_movers, declining). Aggregated in SQL — never sum manually."
    ),
)(product_performance)
# Payments & refunds inspection (read-only; never moves money).
mcp.tool()(get_payment_status)
mcp.tool()(list_refunds)
mcp.tool()(list_payment_issues)
mcp.tool(
    description=(
        "Inspect one refund (or an order's refunds): ledger state plus "
        "computed remaining balance. Read-only, never moves money."
    ),
)(get_refund_status)

mcp_app = mcp.streamable_http_app(
    streamable_http_path="/",
)