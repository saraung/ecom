"""MCP sales & analytics tools (PostgreSQL aggregation, read-only).

All figures come from database-side GROUP BY/SUM/COUNT queries reusing
repositories/analytics.py (which itself enforces the settled_sale() sales
policy). Day boundaries are UTC, matching the REST reports. Nothing here
writes, and no per-order data leaves this module — only aggregates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from app.db.database import engine
from app.mcp.tools import money_envelope
from app.mcp.auth import MCPAuthError
from app.mcp.guards import (
    MCPForbiddenError,
    REPORTS_VIEW,
    require_mcp_perm,
)
from app.repositories import analytics as analytics_repo
from app.repositories import product_image as product_image_repo

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50
MAX_RANGE_DAYS = 366

PRESETS = ("today", "yesterday", "last_7", "last_30", "month")
GROUP_BYS = ("day", "week", "month")
PERF_VIEWS = ("top_units", "top_revenue", "by_category", "slow", "declining")


def _parse_date(value, field: str):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except (ValueError, AttributeError, TypeError):
        return f"{field} must be a YYYY-MM-DD date"


def _resolve_range(preset, from_date, to_date):
    """Preset or explicit range -> (from, to); error string on invalid input.

    Explicit from_date + to_date always win (pass preset=null alongside
    them); otherwise the preset applies (default last_7).
    """
    today = datetime.now(timezone.utc).date()
    explicit_start = _parse_date(from_date, "from_date") if from_date is not None else None
    explicit_end = _parse_date(to_date, "to_date") if to_date is not None else None
    if isinstance(explicit_start, str):
        return explicit_start
    if isinstance(explicit_end, str):
        return explicit_end
    if explicit_start is not None and explicit_end is not None:
        if explicit_start > explicit_end:
            return "from_date must not be after to_date"
        if (explicit_end - explicit_start).days + 1 > MAX_RANGE_DAYS:
            return f"Date range must not exceed {MAX_RANGE_DAYS} days"
        return explicit_start, explicit_end
    if preset is None:
        return "Provide preset or both from_date and to_date"
    cleaned = str(preset).strip().lower()
    if cleaned not in PRESETS:
        return f"preset must be one of: {', '.join(PRESETS)}"
    if cleaned == "today":
        return today, today
    if cleaned == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if cleaned == "last_7":
        return today - timedelta(days=6), today
    if cleaned == "last_30":
        return today - timedelta(days=29), today
    return today.replace(day=1), today  # month to date


def _previous_period(start: date, end: date):
    """Equal-length period immediately before [start, end]."""
    length = (end - start).days + 1
    return end - timedelta(days=2 * length - 1), end - timedelta(days=length)


def _pct_change(current: float, previous: float):
    if previous == 0:
        return None
    return round((current - previous) / abs(previous) * 100, 1)


def _check_auth(ctx, token):
    try:
        require_mcp_perm(ctx, token, REPORTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()
    return None


def _clamp_limit(limit) -> int | str:
    try:
        eff = DEFAULT_LIST_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError):
        return "limit must be an integer"
    return max(1, min(eff, MAX_LIST_LIMIT))


async def sales_summary(
    preset: str | None = "last_7",
    from_date: str | None = None,
    to_date: str | None = None,
    compare: bool = True,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Revenue, orders, AOV, status/payment/refund breakdowns + comparison.

    Revenue counts settled sales only (paid + fulfilled-track statuses);
    pending/cancelled/refunded/COD-uncollected contribute 0. Collected is
    the settled gross (captured, incl. collected COD); refunded is the
    recorded refund_amount sum. Payment rows count records, not charges.
    Pass preset=null with explicit from_date + to_date for custom ranges
    (e.g. full calendar months); explicit dates always win over presets.
    """
    denied = _check_auth(ctx, token)
    if denied is not None:
        return denied

    resolved = _resolve_range(preset, from_date, to_date)
    if isinstance(resolved, str):
        return {"success": False, "error": resolved}
    start, end = resolved

    with Session(engine) as session:
        report = analytics_repo.get_sales_report(session, start, end)
        statuses = analytics_repo.get_order_statistics(session, start, end)
        totals = analytics_repo.revenue_totals(session, start, end)
        payments = analytics_repo.payment_status_summary(session, start, end)
        ledger = analytics_repo.refund_ledger_summary(session, start, end)

        summary = {
            "revenue": report["summary"]["total_sales"],
            "orders": report["summary"]["order_count"],
            "average_order_value": report["summary"]["average_order_value"],
            "collected": totals["gross"],
            "refunded": totals["refunds"],
            "discounts": totals["discounts"],
            "tax": totals["tax"],
            "shipping": totals["shipping"],
            "by_status": statuses["by_status"],
            "total_orders_any_status": statuses["total_orders"],
            "payments_by_status": payments,
            "refund_ledger_by_status": ledger,
        }
        comparison = None
        if compare:
            pstart, pend = _previous_period(start, end)
            prev = analytics_repo.get_sales_report(session, pstart, pend)
            comparison = {
                "previous_from": pstart.isoformat(),
                "previous_to": pend.isoformat(),
                "revenue": prev["summary"]["total_sales"],
                "orders": prev["summary"]["order_count"],
                "average_order_value": prev["summary"]["average_order_value"],
                "revenue_change_pct": _pct_change(
                    summary["revenue"], prev["summary"]["total_sales"]),
                "orders_change_pct": _pct_change(
                    summary["orders"], prev["summary"]["order_count"]),
            }

    return {
        "success": True,
        "period": {"from": start.isoformat(), "to": end.isoformat(), "utc": True},
        "summary": summary,
        "comparison": comparison,
        **money_envelope(),
    }


async def sales_trend(
    preset: str | None = "last_7",
    from_date: str | None = None,
    to_date: str | None = None,
    group_by: str = "day",
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Per-period revenue/order series (day zero-filled, week/month as grouped)."""
    denied = _check_auth(ctx, token)
    if denied is not None:
        return denied

    resolved = _resolve_range(preset, from_date, to_date)
    if isinstance(resolved, str):
        return {"success": False, "error": resolved}
    start, end = resolved
    grouping = str(group_by or "day").strip().lower()
    if grouping not in GROUP_BYS:
        return {"success": False, "error": f"group_by must be one of: {', '.join(GROUP_BYS)}"}

    with Session(engine) as session:
        report = analytics_repo.get_sales_report(session, start, end, group_by=grouping)
        points = [
            {
                "period": row["period"],
                "revenue": row["total_sales"],
                "orders": row["order_count"],
                "average_order_value": row["average_order_value"],
            }
            for row in report["period_data"]
        ]
        if grouping == "day":
            known = {p["period"]: p for p in points}
            points = []
            cursor = start
            while cursor <= end:
                iso = cursor.isoformat()
                points.append(known.get(
                    iso,
                    {"period": iso, "revenue": 0.0, "orders": 0, "average_order_value": 0.0},
                ))
                cursor += timedelta(days=1)

    return {
        "success": True,
        "period": {"from": start.isoformat(), "to": end.isoformat(),
                   "group_by": grouping, "utc": True},
        "points": points,
        "point_count": len(points),
        **money_envelope(),
    }


async def product_performance(
    view: str = "top_revenue",
    limit: int | None = None,
    days: int = 30,
    min_prior_units: int = 5,
    drop_pct: float = 0.5,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Product analytics by view: top_units | top_revenue | by_category |
    slow (zero settled sales in window) | declining (recent drop vs prior).

    Top views rank the full window server-side (up to 200 rows) before
    taking the requested top N, so rank order is exact. Top rows carry
    `image_url` (primary image, one extra query — same pattern as the
    dashboard widget) so chat cards can render; a product card renders
    automatically from returned product rows — describe in text, never
    paste image URLs or markdown images yourself. Always let this tool
    run before describing ranked products, even when names are already
    in context, so the cards render every time.
    """
    denied = _check_auth(ctx, token)
    if denied is not None:
        return denied

    cleaned_view = str(view or "").strip().lower()
    if cleaned_view not in PERF_VIEWS:
        return {"success": False, "error": f"view must be one of: {', '.join(PERF_VIEWS)}"}
    eff_limit = _clamp_limit(limit)
    if isinstance(eff_limit, str):
        return {"success": False, "error": eff_limit}
    try:
        eff_days = int(days)
    except (TypeError, ValueError):
        return {"success": False, "error": "days must be an integer"}
    if not 1 <= eff_days <= MAX_RANGE_DAYS:
        return {"success": False, "error": f"days must be between 1 and {MAX_RANGE_DAYS}"}

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=eff_days - 1)

    with Session(engine) as session:
        if cleaned_view in ("top_units", "top_revenue"):
            rows = analytics_repo.get_top_products(
                session, limit=200, from_date=start, to_date=today)
            key = "total_quantity_sold" if cleaned_view == "top_units" else "total_revenue"
            rows = sorted(rows, key=lambda r: (r[key] or 0), reverse=True)[:eff_limit]
            # Primary thumbnails, one extra query (dashboard-widget pattern).
            try:
                from uuid import UUID as _UUID
                thumbs = product_image_repo.get_first_images_for_products(
                    session,
                    [_UUID(r["product_id"]) for r in rows if r.get("product_id")],
                )
            except Exception:
                thumbs = {}
            for r in rows:
                try:
                    r["image_url"] = thumbs.get(_UUID(r["product_id"]))
                except Exception:
                    r["image_url"] = None
            return {
                "success": True,
                "view": cleaned_view,
                "period": {"from": start.isoformat(), "to": today.isoformat(), "utc": True},
                "products": rows,
                "returned_count": len(rows),
                "limit": eff_limit,
                **money_envelope(),
            }
        if cleaned_view == "by_category":
            rows = analytics_repo.category_sales(
                session, limit=eff_limit, from_date=start, to_date=today)
            return {
                "success": True,
                "view": cleaned_view,
                "period": {"from": start.isoformat(), "to": today.isoformat(), "utc": True},
                "categories": rows,
                "returned_count": len(rows),
                "limit": eff_limit,
                **money_envelope(),
            }
        if cleaned_view == "slow":
            rows = analytics_repo.slow_products(session, days=eff_days, limit=eff_limit)
            return {
                "success": True,
                "view": cleaned_view,
                "period": {"from": start.isoformat(), "to": today.isoformat(), "utc": True},
                "products": rows,
                "returned_count": len(rows),
                "limit": eff_limit,
                **money_envelope(),
            }
        try:
            eff_min_prior = int(min_prior_units)
        except (TypeError, ValueError):
            return {"success": False, "error": "min_prior_units must be an integer"}
        if eff_min_prior < 1:
            return {"success": False, "error": "min_prior_units must be at least 1"}
        try:
            eff_drop = float(drop_pct)
        except (TypeError, ValueError):
            return {"success": False, "error": "drop_pct must be a number"}
        if not 0 < eff_drop <= 1:
            return {"success": False, "error": "drop_pct must be between 0 (exclusive) and 1"}
        rows = analytics_repo.declining_products(
            session, days=eff_days, min_prior_units=eff_min_prior,
            drop_ratio=eff_drop, limit=eff_limit)
        return {
            "success": True,
            "view": cleaned_view,
            "period": {"from": start.isoformat(), "to": today.isoformat(), "utc": True},
            "rule": {
                "window_days": eff_days,
                "min_prior_units": eff_min_prior,
                "drop_pct": eff_drop,
            },
            "products": rows,
            "returned_count": len(rows),
            "limit": eff_limit,
            **money_envelope(),
        }
