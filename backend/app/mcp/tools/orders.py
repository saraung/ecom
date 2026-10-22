"""MCP order tools (real PostgreSQL).

Exposed tools: get_order, list_orders (read-only), cancel_order (write,
two-step confirmed). All reuse require_mcp_perm guards and the existing
repository/service layers. cancel_order executes exclusively through the
shared app/services/order_cancel.py business logic.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
import hashlib

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.core.config import settings
from app.db.database import engine
from app.mcp.tools import money_envelope
from app.models.order import OrderStatus
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.repositories import product_image as product_image_repo
from app.mcp.auth import MCPAuthError, parse_user_id
from app.mcp.guards import (
    MCPForbiddenError,
    ORDERS_REFUND,
    ORDERS_UPDATE,
    ORDERS_VIEW,
    require_mcp_perm,
)
from app.repositories.order import (
    get_all_orders_with_filters,
    get_order_by_id,
    get_order_by_number,
)
from app.services import order_cancel as order_cancel_service
from app.services import refund_service

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50

VALID_STATUSES = tuple(s.value for s in OrderStatus)

# payment_status is a free-form str column; these are the values the
# codebase itself writes/reads (order_expiry, payment_settlement,
# webhooks, admin/cod, refunds).
VALID_PAYMENT_STATUSES = frozenset(
    {
        "pending",
        "paid",
        "failed",
        "cod_pending",
        "refund_failed",
        "refund_initiated",
        "refund_completed",
    }
)


def _order_summary(order) -> dict:
    """Safe whitelist shared by get_order/list_orders (no PII, no secrets)."""
    status = getattr(order.status, "value", order.status)
    placed = order.placed_at.isoformat() if order.placed_at is not None else None
    try:
        total = float(order.grand_total)
    except (TypeError, ValueError):
        total = str(order.grand_total)
    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "status": str(status) if status is not None else None,
        "payment_status": order.payment_status,
        "grand_total": total,
        "placed_at": placed,
        "user_id": str(order.user_id),
    }


def _order_item_summary(item) -> dict:
    """Safe per-line whitelist: snapshot name/sku/attrs + qty + money.

    Mirrors the admin detail items_payload minus product_id/image links —
    enough for the agent to answer "what is the product?" verbatim without
    guessing from grand_total. Missing variant/product rows degrade to the
    stored snapshot (never None-crash, never PII).
    """
    try:
        unit = float(item.unit_price)
    except (TypeError, ValueError):
        unit = str(getattr(item, "unit_price", None))
    try:
        total = float(item.line_total)
    except (TypeError, ValueError):
        total = str(getattr(item, "line_total", None))
    try:
        attrs = dict(getattr(item, "variant_attributes", None) or {})
    except (TypeError, ValueError, AttributeError):
        attrs = {}
    return {
        "product_name": getattr(item, "product_name", None),
        "variant_sku": getattr(item, "variant_sku", None),
        "variant_attributes": attrs,
        "quantity": getattr(item, "quantity", None),
        "unit_price": unit,
        "line_total": total,
    }


def _order_items(order, cap: int = 50) -> list[dict]:
    try:
        raw = list(order.items or [])
    except Exception:
        return []
    return [_order_item_summary(i) for i in raw[:cap]]


def _order_product_cards(order, session, cap: int = 4) -> list[dict]:
    """Card-ready product rows for the chat UI, resolved from order items.

    Order items are variant snapshots: item.variant_id -> product -> slug +
    first image (same resolution as the admin order detail). Whitelisted
    display fields only (id/name/slug/price/image_url). Missing variant or
    product rows degrade to no card for that line, never a crash.
    """
    try:
        raw = list(order.items or [])
    except Exception:
        return []
    variant_ids = [
        item.variant_id for item in raw if getattr(item, "variant_id", None) is not None
    ]
    if not variant_ids:
        return []
    variants = session.exec(
        select(ProductVariant).where(ProductVariant.id.in_(variant_ids))
    ).all()
    variant_to_product = {variant.id: variant.product_id for variant in variants}
    product_ids = list(set(variant_to_product.values()))
    if not product_ids:
        return []
    products = session.exec(select(Product).where(Product.id.in_(product_ids))).all()
    product_slug = {product.id: product.slug for product in products}
    first_images = product_image_repo.get_first_images_for_products(session, product_ids)

    cards: list[dict] = []
    seen: set = set()
    for item in raw:
        product_id = variant_to_product.get(getattr(item, "variant_id", None))
        if product_id is None or product_id in seen:
            continue
        seen.add(product_id)
        try:
            price = float(item.unit_price)
        except (TypeError, ValueError):
            price = None
        cards.append(
            {
                "id": str(product_id),
                "name": getattr(item, "product_name", None),
                "slug": product_slug.get(product_id),
                "price": price,
                "compare_at_price": None,
                "image_url": first_images.get(product_id),
                "stock": None,
                "is_active": None,
            }
        )
        if len(cards) >= cap:
            break
    return cards


async def get_order(
    order_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Get an order by UUID or order_number (real PostgreSQL, read-only).

    Auth: reuses require_mcp_perm(..., "orders.view") — same JWT + admin
    audience + DB RBAC gate as the REST admin API. Read-only: only SELECTs
    via app/repositories/order.py, never commit/add/delete/update.
    Returns a safe whitelist plus item_count and items (line-item
    snapshots: product_name, variant_sku, quantity, unit_price,
    line_total — quote verbatim, never infer products from grand_total).
    Also returns product_cards: card-ready display rows (id/name/slug/price/
    image_url) resolved from the item variants, consumed by the chat UI —
    never raw tool internals, never LLM-written URLs.
    """

    try:
        require_mcp_perm(ctx, token, ORDERS_VIEW)
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
        order = None
        try:
            order_uuid = uuid.UUID(ref)
        except (ValueError, AttributeError, TypeError):
            order_uuid = None
        if order_uuid is not None:
            order = get_order_by_id(session, order_uuid)
        if order is None:
            order = get_order_by_number(session, ref)
        if order is None:
            return {"success": False, "error": f"Order {ref} not found"}

        try:
            items = _order_items(order)
            item_count = len(order.items or [])
        except Exception:
            items = []
            item_count = None
        result = {
            "success": True,
            "order": {**_order_summary(order), "item_count": item_count, "items": items},
            **money_envelope(),
        }
        try:
            cards = _order_product_cards(order, session)
        except Exception:
            cards = []
        if cards:
            result["product_cards"] = cards
        return result


async def list_orders(
    status: str | None = None,
    payment_status: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """List order summaries (real PostgreSQL, read-only, paginated).

    Filtering, sorting, counting, and limiting all happen in PostgreSQL
    via get_all_orders_with_filters — the tool never loads the full
    dataset into Python. `limit` is clamped server-side to MAX_LIST_LIMIT.
    `from_date`/`to_date` are YYYY-MM-DD dates filtering placed_at
    (to_date covers the whole day).
    Returns the same safe whitelist as get_order (without item_count).
    """

    try:
        require_mcp_perm(ctx, token, ORDERS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    norm_status = None
    if status is not None:
        cleaned = str(status).strip().lower()
        if cleaned:
            try:
                # Enum member binds correctly on every backend.
                norm_status = OrderStatus(cleaned)
            except ValueError:
                return {
                    "success": False,
                    "error": (
                        f"Invalid status '{status}'. "
                        f"Valid values: {', '.join(VALID_STATUSES)}"
                    ),
                }

    norm_payment = None
    if payment_status is not None:
        cleaned = str(payment_status).strip().lower()
        if cleaned:
            if cleaned not in VALID_PAYMENT_STATUSES:
                return {
                    "success": False,
                    "error": (
                        f"Invalid payment_status '{payment_status}'. "
                        f"Valid values: {', '.join(sorted(VALID_PAYMENT_STATUSES))}"
                    ),
                }
            norm_payment = cleaned

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

    parsed_from = None
    if from_date is not None:
        try:
            parsed_from = date.fromisoformat(str(from_date).strip())
        except (ValueError, AttributeError, TypeError):
            return {"success": False, "error": "from_date must be a YYYY-MM-DD date"}
    parsed_to = None
    if to_date is not None:
        try:
            parsed_to = date.fromisoformat(str(to_date).strip())
        except (ValueError, AttributeError, TypeError):
            return {"success": False, "error": "to_date must be a YYYY-MM-DD date"}
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        return {"success": False, "error": "from_date must not be after to_date"}

    # The repository filters placed_at <= to_date, and a bare date binds as
    # midnight — so lift to_date to end-of-day to make ranges day-inclusive
    # ("today".."today" must cover the whole day). from_date binds as
    # midnight, already day-start inclusive. Echoes below still show the
    # user-supplied dates. Shared repo semantics are untouched.
    inclusive_to = (
        datetime.combine(parsed_to + timedelta(days=1), time.min)
        if parsed_to is not None
        else None
    )

    with Session(engine) as session:
        orders, total = get_all_orders_with_filters(
            session,
            skip=eff_offset,
            limit=eff_limit,
            status=norm_status,
            payment_status=norm_payment,
            from_date=parsed_from,
            to_date=inclusive_to,
        )
        items = [_order_summary(order) for order in orders]

    return {
        "success": True,
        "orders": items,
        "returned_count": len(items),
        "total_matching": total,
        "limit": eff_limit,
        "offset": eff_offset,
        "from_date": parsed_from.isoformat() if parsed_from else None,
        "to_date": parsed_to.isoformat() if parsed_to else None,
        **money_envelope(),
    }


CANCEL_PREVIEW_TTL_MINUTES = 10
CANCEL_PREVIEW_TYPE = "mcp_cancel_preview"
DEFAULT_CANCEL_REASON = "Cancelled via MCP agent"


def _issue_cancel_preview(user_id: UUID, order) -> str:
    """Signed, expiring, order-and-status-bound preview token (no storage)."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=CANCEL_PREVIEW_TTL_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "oid": str(order.id),
            "st": order.status.value,
            "exp": expire,
            "type": CANCEL_PREVIEW_TYPE,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def _cancel_implications(order) -> dict:
    """Money/stock/audit consequences, computed from live policy and state.

    Read-only: figures come from refund_service.calculate_refund keyed on
    the order's CURRENT (pre-cancel) status. No money moves here.
    """
    paid_online = order.payment_method != "cod" and order.payment_status == "paid"
    if not paid_online:
        return {
            "money_moves": False,
            "message": (
                "No money moves: this order holds no captured online payment. "
                "Cancelling restores stock and records an audit entry only."
            ),
        }
    policy = refund_service.calculate_refund(order, order.status)
    return {
        "money_moves": False,
        "refundable_amount": str(policy["refund_amount"]),
        "restocking_fee": str(policy["restocking_fee"]),
        "fee_percentage": policy["fee_percentage"],
        "message": (
            "Refund NOT executed: captured funds stay with the store. "
            f"Refundable balance left open: {policy['refund_amount']} "
            f"(restocking fee {policy['restocking_fee']}). Claim it through "
            "the existing refund flow, which requires orders.refund permission."
        ),
    }


def _resolve_order_ref(session: Session, ref: str):
    order = None
    try:
        order_uuid = uuid.UUID(ref)
    except (ValueError, AttributeError, TypeError):
        order_uuid = None
    if order_uuid is not None:
        order = get_order_by_id(session, order_uuid)
    if order is None:
        order = get_order_by_number(session, ref)
    return order


async def cancel_order(
    order_id: str | int | None = None,
    reason: str | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then execute an order cancellation (two-step, confirmed only).

    Step 1 (confirmed falsy): validates orders.update + order state, makes
    NO change, returns the preview, implications, and a signed expiring
    preview token. Step 2 (confirmed true + preview token): re-resolves
    the caller, re-checks permission, verifies the token (same user, same
    order, same status, unexpired), re-locks the row, re-validates state,
    then executes through the shared order_cancel service (cancel + restock
    + email + audit, refund_choice="later": money never moves).
    Single-use follows from the status match under lock: after the first
    commit the order is CANCELLED, so replays/concurrent retries fail the
    state check instead of acting twice.
    """
    try:
        user_info, _ = require_mcp_perm(ctx, token, ORDERS_UPDATE)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if order_id is None:
        return {"success": False, "error": "order_id is required"}
    ref = str(order_id).strip()
    if not ref:
        return {"success": False, "error": "order_id is required"}

    text_reason = (reason or "").strip() or DEFAULT_CANCEL_REASON
    if len(text_reason) > 500:
        return {"success": False, "error": "reason must be at most 500 characters"}

    user_id = parse_user_id(user_info)
    if user_id is None:
        return {"success": False, "error": "Could not validate credentials"}

    with Session(engine) as session:
        order = _resolve_order_ref(session, ref)
        if order is None:
            return {"success": False, "error": f"Order {ref} not found"}

        if not confirmed:
            try:
                order_cancel_service.validate_cancellable(order)
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else "Order cannot be cancelled"
                return {"success": False, "error": detail}
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": _issue_cancel_preview(user_id, order),
                "expires_in_minutes": CANCEL_PREVIEW_TTL_MINUTES,
                "order": _order_summary(order),
                "cancel_implications": _cancel_implications(order),
                **money_envelope(),
            }

        # ---- Execution: trust nothing from the client; re-verify all. ----
        # Preview-token check first so a stale preview reports as stale even
        # when the order has since moved to a terminal state; the shared
        # service re-validates state under lock immediately afterwards.
        if not preview_token or not str(preview_token).strip():
            return {"success": False, "error": "A fresh preview_token is required to execute cancellation"}
        try:
            preview = jwt.decode(
                str(preview_token).strip(),
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError:
            return {"success": False, "error": "Invalid or expired preview_token; request a new preview"}
        if (
            preview.get("type") != CANCEL_PREVIEW_TYPE
            or preview.get("sub") != str(user_id)
            or preview.get("oid") != str(order.id)
            or preview.get("st") != order.status.value
        ):
            return {
                "success": False,
                "error": "Preview is stale (order changed since preview); request a new preview",
            }

        actor = session.get(User, user_id)
        if actor is None or not actor.is_active:
            return {"success": False, "error": "Could not validate credentials"}
        try:
            result = order_cancel_service.cancel_order_as_admin(
                session,
                order_id=order.id,
                actor=actor,
                reason=text_reason,
                refund_choice="later",
                restock=True,
                notify_customer=True,
                request=None,
                commit=True,
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Order cannot be cancelled"
            return {"success": False, "error": detail}
        return {
            "success": True,
            "cancelled": True,
            "order_id": result["order_id"],
            "order_number": result["order_number"],
            "status": result["status"],
            "refund": result["refund"],
            **money_envelope(),
        }


REFUND_PREVIEW_TTL_MINUTES = 10
REFUND_PREVIEW_TYPE = "mcp_refund_preview"
DEFAULT_REFUND_REASON = "Refund via MCP agent"


def _refund_basis(session: Session, order):
    """Fee basis mirroring request_admin_refund: pre-cancel status when known."""
    if order.status == OrderStatus.CANCELLED:
        return refund_service.status_at_cancellation(session, order)
    return order.status


def _preview_remaining(session: Session, order, basis):
    """Live refundable balance, same inputs as request_admin_refund (read-only)."""
    from app.core.store_settings import get_store_settings
    from app.services.product_return import unexecuted_return_reserve

    policy = get_store_settings(session, seed=False)
    calc = refund_service.calculate_refund(order, basis, policy=policy)
    remaining = calc["refund_amount"] - unexecuted_return_reserve(session, order)
    return max(remaining, Decimal(0)), calc


def _parse_refund_amount(value) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return amount.quantize(Decimal("0.01"))


def _issue_refund_preview(user_id: UUID, order, basis, amount: Decimal, reason: str, key: str) -> str:
    """Signed, expiring preview token binding user/order/amount/reason/basis/key."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=REFUND_PREVIEW_TTL_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "oid": str(order.id),
            "amt": str(amount),
            "rhash": hashlib.sha256(reason.encode()).hexdigest(),
            "basis": basis.value,
            "key": key,
            "exp": expire,
            "type": REFUND_PREVIEW_TYPE,
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


async def issue_refund(
    order_id: str | int | None = None,
    amount=None,
    reason: str | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then execute a refund (two-step, confirmed only).

    Step 1 (confirmed falsy): validates orders.refund + payment/refund
    state, recomputes the live refundable balance, pre-checks authority,
    makes NO change and returns the preview with a signed expiring token
    binding user, order, amount, reason, fee basis, and the server-derived
    idempotency key. Step 2 (confirmed true + token): re-resolves the
    caller, re-checks permission, verifies the token, recomputes the
    balance, then executes through request_admin_refund (role limits,
    second-admin staging, ledger idempotency, PSP reconciliation). Money
    moves only inside that canonical function; a staged approval reports
    honestly as not-processed.
    """
    try:
        user_info, _ = require_mcp_perm(ctx, token, ORDERS_REFUND)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if order_id is None:
        return {"success": False, "error": "order_id is required"}
    ref = str(order_id).strip()
    if not ref:
        return {"success": False, "error": "order_id is required"}

    text_reason = (reason or "").strip() or DEFAULT_REFUND_REASON
    if len(text_reason) > 500:
        return {"success": False, "error": "reason must be at most 500 characters"}

    user_id = parse_user_id(user_info)
    if user_id is None:
        return {"success": False, "error": "Could not validate credentials"}

    with Session(engine) as session:
        order = _resolve_order_ref(session, ref)
        if order is None:
            return {"success": False, "error": f"Order {ref} not found"}

        if not confirmed:
            if order.payment_method == "cod" or order.payment_status not in ("paid", "refund_failed"):
                return {"success": False, "error": "Order holds no captured online payment to refund"}
            basis = _refund_basis(session, order)
            remaining, calc = _preview_remaining(session, order, basis)
            if remaining <= 0:
                return {"success": False, "error": "Nothing to refund (order already fully refunded)"}
            requested = _parse_refund_amount(amount)
            if amount is not None and requested is None:
                return {"success": False, "error": "amount must be a positive number"}
            if requested is not None and requested <= 0:
                return {"success": False, "error": "amount must be a positive number"}
            if requested is not None and requested > remaining:
                return {
                    "success": False,
                    "error": f"amount exceeds refundable balance of {remaining}",
                }
            target = remaining if requested is None else requested
            actor = session.get(User, user_id)
            if actor is None or not actor.is_active:
                return {"success": False, "error": "Could not validate credentials"}
            gate = refund_service.refund_authorization(session, actor, order, target)
            key = f"refund-mcp-{order.id}-{basis.value}"
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": _issue_refund_preview(user_id, order, basis, target, text_reason, key),
                "expires_in_minutes": REFUND_PREVIEW_TTL_MINUTES,
                "order": _order_summary(order),
                "amount": str(target),
                "reason": text_reason,
                "restocking_fee": str(calc["restocking_fee"]),
                "fee_percentage": calc["fee_percentage"],
                "remaining_before": str(remaining),
                # Labeled breakdown for presentation (display only — the
                # fee is already deducted inside calculate_refund, so the
                # refund figure below is final and nothing is deducted again
                # at execution).
                "order_total": str(order.grand_total),
                "refund_to_customer": str(target),
                "additional_fee_at_execution": "0.00",
                "requires_approval": gate["requires_approval"],
                "approval_reason": gate["reason"],
                "idempotency_key": key,
                **money_envelope(),
            }

        # ---- Execution: trust nothing from the client; re-verify all. ----
        if not preview_token or not str(preview_token).strip():
            return {"success": False, "error": "A fresh preview_token is required to execute a refund"}
        try:
            preview = jwt.decode(
                str(preview_token).strip(),
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError:
            return {"success": False, "error": "Invalid or expired preview_token; request a new preview"}
        if (
            preview.get("type") != REFUND_PREVIEW_TYPE
            or preview.get("sub") != str(user_id)
            or preview.get("oid") != str(order.id)
        ):
            return {
                "success": False,
                "error": "Preview does not match this user or order; request a new preview",
            }

        # Recompute basis + balance fresh: reserves/fees may have moved.
        basis = _refund_basis(session, order)
        if preview.get("basis") != basis.value or preview.get("key") != f"refund-mcp-{order.id}-{basis.value}":
            return {
                "success": False,
                "error": "Preview is stale (order changed since preview); request a new preview",
            }
        remaining, _ = _preview_remaining(session, order, basis)
        token_amount = _parse_refund_amount(preview.get("amt"))
        if (
            token_amount is None
            or token_amount <= 0
            or token_amount > remaining
            or preview.get("rhash") != hashlib.sha256(text_reason.encode()).hexdigest()
        ):
            return {
                "success": False,
                "error": "Preview is stale (amount or reason changed); request a new preview",
            }

        actor = session.get(User, user_id)
        if actor is None or not actor.is_active:
            return {"success": False, "error": "Could not validate credentials"}
        try:
            result = refund_service.request_admin_refund(
                session,
                order,
                requested_by=actor,
                reason=text_reason,
                amount=token_amount,
                idempotency_key=preview["key"],
                status_at=basis,
                notify_customer=True,
                commit=True,
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Refund failed"
            return {"success": False, "error": detail}
        if result.get("requires_approval"):
            return {
                "success": True,
                "approval_staged": True,
                "processed": False,
                "amount": str(result.get("amount")),
                "refund_row_id": result.get("refund_row_id"),
                "message": result.get("message"),
                **money_envelope(),
            }
        if result.get("processed"):
            return {
                "success": True,
                "refunded": True,
                "processed": True,
                "duplicate": bool(result.get("duplicate")),
                "amount": str(result.get("amount")),
                "refund_id": result.get("refund_id"),
                "status": result.get("status"),
                "refund_row_id": result.get("refund_row_id"),
                "message": result.get("message"),
                **money_envelope(),
            }
        return {"success": False, "error": result.get("message", "Refund failed")}
