"""MCP payments & refunds inspection tools (strictly read-only).

Payment state comes from local rows; refund state from the ledger plus an
optional single live provider lookup. No capture, approval, issuance,
reconciliation, or mutation happens here — those stay on their REST paths.
A dummy/unconfigured provider is never reported as verified success.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from app.db.database import engine
from app.mcp.tools import money_envelope
from app.models.order import Order
from app.models.refund import Refund, RefundStatus
from app.mcp.auth import MCPAuthError
from app.mcp.guards import (
    MCPForbiddenError,
    ORDERS_REFUND,
    PAYMENTS_VIEW,
    require_mcp_perm,
)
from app.repositories import payment as payment_repo
from app.repositories import refund as refund_repo
from app.services import refund_service
from app.services.payment_service import DummyPaymentService

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50
LIVE_TIMEOUT_SECONDS = 10.0

VALID_REFUND_STATUSES = tuple(s.value for s in RefundStatus)


def _payment_summary(payment) -> dict:
    status = getattr(payment.status, "value", payment.status)
    provider = getattr(payment.provider, "value", payment.provider)
    return {
        "id": str(payment.id),
        "status": str(status) if status is not None else None,
        "amount": float(payment.amount or 0),
        "currency": payment.currency,
        "provider": str(provider) if provider is not None else None,
        "last_four": payment.last_four,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
    }


def _refund_summary(row, order_number: str | None = None) -> dict:
    status = getattr(row.status, "value", row.status)
    return {
        "id": str(row.id),
        "order_id": str(row.order_id),
        "order_number": order_number,
        "amount": float(row.amount or 0),
        "restocking_fee": float(row.restocking_fee or 0),
        "status": str(status) if status is not None else None,
        "reason": row.reason,
        "requested_by": str(row.requested_by) if row.requested_by else None,
        "approved_by": str(row.approved_by) if row.approved_by else None,
        "provider_refund_id": row.provider_refund_id,
        "provider_status": row.provider_status,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def _order_numbers(session: Session, order_ids: set) -> dict:
    """Batch order_number lookup (single query, no N+1)."""
    if not order_ids:
        return {}
    rows = session.exec(
        select(Order.id, Order.order_number).where(Order.id.in_(order_ids))
    ).all()
    return {str(row[0]): row[1] for row in rows}


def _resolve_order_ref(session: Session, ref: str):
    from app.mcp.tools.orders import _resolve_order_ref

    return _resolve_order_ref(session, ref)


async def get_payment_status(
    order_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Payment rows and collection state for one order (local rows only)."""
    try:
        require_mcp_perm(ctx, token, PAYMENTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if order_id is None:
        return {"success": False, "error": "order_id is required"}
    ref = str(order_id).strip()
    if not ref:
        return {"success": False, "error": "order_id is required"}

    with Session(engine) as session:
        order = _resolve_order_ref(session, ref)
        if order is None:
            return {"success": False, "error": f"Order {ref} not found"}
        payments = payment_repo.get_payments_by_order(session, order.id)
        rows = [_payment_summary(p) for p in payments]
        collected = any(
            str(getattr(p.status, "value", p.status)) == "succeeded" for p in payments
        )
    return {
        "success": True,
        "order_id": str(order.id),
        "order_number": order.order_number,
        "payment_status": order.payment_status,
        "grand_total": float(order.grand_total or 0),
        "refund_amount": float(order.refund_amount or 0),
        "collected": collected,
        "payments": rows,
        "payment_count": len(rows),
        **money_envelope(),
    }


async def list_refunds(
    status: str | None = None,
    order_id: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Paginated refund ledger rows with optional status/order filters."""
    try:
        require_mcp_perm(ctx, token, ORDERS_REFUND)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    norm_status = None
    if status is not None:
        cleaned = str(status).strip().lower()
        if cleaned:
            try:
                norm_status = RefundStatus(cleaned)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Invalid status '{status}'. "
                             f"Valid values: {', '.join(VALID_REFUND_STATUSES)}",
                }
    norm_order_id = None
    if order_id is not None:
        cleaned = str(order_id).strip()
        if cleaned:
            try:
                norm_order_id = uuid.UUID(cleaned)
            except (ValueError, AttributeError, TypeError):
                return {"success": False, "error": "order_id must be a UUID"}
    try:
        eff_limit = DEFAULT_LIST_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError):
        return {"success": False, "error": "limit must be an integer"}
    eff_limit = max(1, min(eff_limit, MAX_LIST_LIMIT))
    try:
        eff_offset = 0 if offset is None else int(offset)
    except (TypeError, ValueError):
        return {"success": False, "error": "offset must be an integer"}
    eff_offset = max(0, eff_offset)

    with Session(engine) as session:
        rows, total = refund_repo.list_refunds(
            session, skip=eff_offset, limit=eff_limit,
            status=norm_status, order_id=norm_order_id,
        )
        numbers = _order_numbers(session, {r.order_id for r in rows})
        items = [
            _refund_summary(r, numbers.get(str(r.order_id))) for r in rows
        ]
    return {
        "success": True,
        "refunds": items,
        "returned_count": len(items),
        "total_matching": total,
        "limit": eff_limit,
        "offset": eff_offset,
        **money_envelope(),
    }


async def list_payment_issues(
    limit: int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Unresolved refund work: cancelled paid-online orders holding captured
    money with no refund in flight. Same shared helper as the REST
    attention route (identical filters, ordering, limits). Read-only."""
    try:
        require_mcp_perm(ctx, token, ORDERS_REFUND)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    try:
        eff_limit = DEFAULT_LIST_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError):
        return {"success": False, "error": "limit must be an integer"}
    eff_limit = max(1, min(eff_limit, MAX_LIST_LIMIT))

    with Session(engine) as session:
        result = refund_service.get_attention_queue(session, limit=eff_limit)
    return {
        "success": True,
        "count": result["count"],
        "orders": result["orders"],
        "limit": eff_limit,
        **money_envelope(),
    }


async def get_refund_status(
    refund_id: str | None = None,
    order_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Inspect one refund (or an order's refunds): ledger state, computed
    remaining balance, and at most ONE live provider lookup, guarded by a
    timeout. Timeouts and provider errors return cached state labeled
    stale/unknown — never a claimed success. A dummy/unconfigured provider
    is reported as unverified, never as success.
    """
    try:
        require_mcp_perm(ctx, token, ORDERS_REFUND)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    has_refund = refund_id is not None and str(refund_id).strip() != ""
    has_order = order_id is not None and str(order_id).strip() != ""
    if has_refund == has_order:
        return {"success": False, "error": "Provide exactly one of refund_id or order_id"}

    with Session(engine) as session:
        rows: list = []
        order = None
        if has_refund:
            try:
                rid = uuid.UUID(str(refund_id).strip())
            except (ValueError, AttributeError, TypeError):
                return {"success": False, "error": "refund_id must be a UUID"}
            row = refund_repo.get_by_id(session, rid)
            if row is None:
                return {"success": False, "error": f"Refund {refund_id} not found"}
            rows = [row]
            order = session.get(Order, row.order_id)
        else:
            order = _resolve_order_ref(session, str(order_id).strip())
            if order is None:
                return {"success": False, "error": f"Order {order_id} not found"}
            rows = sorted(
                session.exec(
                    select(Refund).where(Refund.order_id == order.id)
                ).all(),
                key=lambda r: (r.created_at is None, r.created_at),
            )

        numbers = _order_numbers(session, {r.order_id for r in rows})
        items = [_refund_summary(r, numbers.get(str(r.order_id))) for r in rows]

        remaining = None
        if order is not None:
            basis = refund_service.status_at_cancellation(session, order)
            calc = refund_service.calculate_refund(order, basis)
            remaining = float(calc["refund_amount"])

        # Live check: newest row carrying a provider id, at most one call.
        live = None
        live_source = "ledger"
        provider_rows = [r for r in rows if r.provider_refund_id]
        target = provider_rows[-1] if provider_rows else None
        service = None
        if target is not None and order is not None:
            payment = refund_service._get_refundable_payment(session, order)
            try:
                service = refund_service.get_payment_service_for_payment(payment) \
                    if payment else None
            except ValueError:
                service = None
        if target is not None and service is not None and not isinstance(
            service, DummyPaymentService
        ):
            refund_id_value = target.provider_refund_id
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(service.get_refund_status, refund_id_value),
                    timeout=LIVE_TIMEOUT_SECONDS,
                )
            except Exception:
                result = None
            if isinstance(result, dict) and result.get("status"):
                live = {
                    "status": result.get("status"),
                    "refund_id": result.get("refund_id") or refund_id_value,
                    "source": "live",
                }
                live_source = "live"
            else:
                live = {
                    "status": "unknown",
                    "refund_id": refund_id_value,
                    "source": "ledger",
                    "stale": True,
                }
        elif target is not None:
            live = {
                "status": "unknown",
                "refund_id": target.provider_refund_id,
                "source": "ledger",
                "stale": True,
                "note": "Provider status unavailable (dummy/unconfigured or no captured payment); "
                        "shown state is local ledger only, not provider-confirmed.",
            }

    return {
        "success": True,
        "refunds": items,
        "returned_count": len(items),
        "remaining_refundable": remaining,
        "live": live,
        "live_source": live_source,
        **money_envelope(),
    }
