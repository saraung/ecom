"""MCP inventory tools (PostgreSQL reads + confirmed adjustments).

Stock lives on ProductVariant.stock; there is no movement ledger, so every
adjustment is a signed delta with a reason, applied under a row lock and
recorded in AdminAuditLog (before/after). Absolute overwrites are refused.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, TypeAlias

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel import Session

from app.db.database import engine
from app.mcp.tools import money_envelope
from app.models.product import Product, ProductVariant
from app.mcp.auth import MCPAuthError, parse_user_id
from app.mcp.guards import (
    MCPForbiddenError,
    INVENTORY_ADJUST,
    PRODUCTS_UPDATE,
    PRODUCTS_VIEW,
    require_mcp_perm,
    require_mcp_perm_any,
)
from app.mcp.preview import (
    WRITE_PREVIEW_TTL_MINUTES,
    issue_write_preview,
    verify_write_preview,
)
from app.repositories import audit as audit_repo
from app.repositories import product as product_repo
from app.mcp.tools.products import _resolve_variant, _variant_summary, _product_summary

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context: TypeAlias = Any


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50
DEFAULT_LOW_STOCK_THRESHOLD = 5

# Fuzzy-fallback bounds for check_stock (few small DB round-trips max).
FUZZY_MAX_PRODUCTS = 5
FUZZY_MAX_CANDIDATES = 5
FUZZY_SKU_SCAN_LIMIT = 10
FUZZY_ATTRIBUTE_SCAN_LIMIT = 50


def _fuzzy_tokens(ref: str) -> list[str]:
    """Lowercase word tokens (len>=2) used for product/variant matching."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", (ref or "").lower())
    seen: list[str] = []
    for word in cleaned.split():
        if len(word) >= 2 and word not in seen:
            seen.append(word)
    return seen


def _variant_fuzzy_score(variant, product, tokens: list[str]) -> tuple[int, list[str]]:
    """Score one variant against tokens; SKU/attribute hits weigh most.

    Per token only the best field counts (SKU, then attribute values, then
    product name/slug), so "blue" matching both SKU and color scores once.
    """
    sku = str(getattr(variant, "sku", "") or "").lower()
    try:
        attr_text = " ".join(
            str(v) for v in (getattr(variant, "attributes", None) or {}).values()
        ).lower()
    except (AttributeError, TypeError, ValueError):
        attr_text = ""
    name = f"{getattr(product, 'name', '')} {getattr(product, 'slug', '')}".lower()
    score = 0
    hits: list[str] = []
    for token in tokens:
        if token in sku:
            score += 2
            hits.append(token)
        elif token in attr_text:
            score += 2
            hits.append(token)
        elif token in name:
            score += 1
            hits.append(token)
    return score, hits


def _fuzzy_stock_lookup(session: Session, ref: str) -> dict | None:
    """Bounded fuzzy variant lookup; None when nothing matches.

    Discovery, in order: product name/slug word search, variant SKU
    substring search (DB-side), and — only when both yield nothing — an
    attribute word scan over the most recent products (variant colors and
    sizes live in JSON attributes that no name index covers). Scoring over
    the already eager-loaded variants needs no further queries. Returns
    single / ambiguous / None shapes for check_stock.
    """
    tokens = _fuzzy_tokens(ref)
    if not tokens:
        return None
    products: list = []
    seen_ids: set = set()

    def _collect(rows):
        for product in rows:
            if product is not None and product.id not in seen_ids:
                seen_ids.add(product.id)
                products.append(product)

    for token in sorted(tokens, key=len, reverse=True):
        rows, _ = product_repo.get_all_products_admin(
            session, skip=0, limit=FUZZY_MAX_PRODUCTS, search=token
        )
        _collect(rows)
        if len(products) >= FUZZY_MAX_PRODUCTS:
            break
    if len(products) < FUZZY_MAX_PRODUCTS:
        for token in sorted(tokens, key=len, reverse=True):
            like = (
                f"%{token.replace(chr(92), chr(92) * 2).replace('%', chr(92) + '%').replace('_', chr(92) + '_')}%"
            )
            rows = session.execute(
                select(ProductVariant)
                .where(ProductVariant.sku.ilike(like, escape="\\"))
                .options(selectinload(ProductVariant.product))
                .limit(FUZZY_SKU_SCAN_LIMIT)
            ).scalars().all()
            _collect([v.product for v in rows])
            if len(products) >= FUZZY_MAX_PRODUCTS:
                break
    if not products:
        # Attribute words (colors, sizes) match no name/SKU index: scan the
        # most recent products and score their variants in memory. Bounded
        # by FUZZY_ATTRIBUTE_SCAN_LIMIT.
        rows, _ = product_repo.get_all_products_admin(
            session, skip=0, limit=FUZZY_ATTRIBUTE_SCAN_LIMIT
        )
        _collect(rows)
    scored: list[tuple[int, list[str], Any, Any]] = []
    for product in products:
        for variant in (product.variants or []):
            score, hits = _variant_fuzzy_score(variant, product, tokens)
            if score > 0:
                scored.append((score, hits, product, variant))
    if not scored:
        return None
    scored.sort(key=lambda row: (-row[0], str(row[3].sku or "")))
    top_score = scored[0][0]
    winners = [row for row in scored if row[0] == top_score][:FUZZY_MAX_CANDIDATES]
    if len(winners) == 1:
        _, hits, product, variant = winners[0]
        return {
            "success": True,
            "variant": _variant_summary(variant),
            "product": _product_summary(product, None),
            "product_name": product.name,
            "match": "fuzzy",
            "matched_on": sorted(set(hits)),
            **money_envelope(),
        }
    names = sorted({row[2].name for row in winners})
    candidates = [
        {**_variant_summary(variant), "product_name": product.name}
        for _, _, product, variant in winners
    ]
    return {
        "success": True,
        "product_id": None,
        "product_name": names[0] if len(names) == 1 else None,
        "variants": candidates,
        "total_stock": sum(int(v["stock"]) for v in candidates),
        "match": "ambiguous",
        "message": (
            f"Multiple variants match '{ref.strip()}'. Ask the user which "
            "variant (SKU) they mean."
        ),
        **money_envelope(),
    }



async def check_stock(
    product_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Stock for one variant SKU/ID, product UUID/slug, or fuzzy words.

    Exact identifiers resolve directly; anything else falls back to a
    bounded product/variant word match (single result flagged
    match=fuzzy, several returned as candidates). A product card renders
    automatically from returned product data — describe in text, never
    paste image URLs or markdown images yourself. Always call a product
    tool before describing any product, even when details are already in
    context, so the card renders every time."""
    try:
        require_mcp_perm(ctx, token, PRODUCTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if product_id is None:
        return {"success": False, "error": "product_id is required"}
    ref = str(product_id).strip()
    if not ref:
        return {"success": False, "error": "product_id is required"}

    with Session(engine) as session:
        variant = _resolve_variant(session, ref)
        if variant is not None:
            return {
                "success": True,
                "variant": _variant_summary(variant),
                "product": _product_summary(variant.product, None)
                if getattr(variant, "product", None) is not None
                else None,
                **money_envelope(),
            }
        try:
            product_uuid = uuid.UUID(ref)
        except (ValueError, AttributeError, TypeError):
            product_uuid = None
        product = (
            product_repo.get_product_by_id(session, product_uuid)
            if product_uuid is not None
            else product_repo.get_product_by_slug(session, ref)
        )
        if product is None:
            fuzzy = _fuzzy_stock_lookup(session, ref)
            if fuzzy is not None:
                return fuzzy
            return {
                "success": False,
                "error": (
                    f"Product {ref} not found. Try a variant SKU, the product "
                    "slug, or fewer/partial words via list_products search."
                ),
            }
        variants = product_repo.get_variants(session, product.id)
        return {
            "success": True,
            "product_id": str(product.id),
            "product_name": product.name,
            "product": _product_summary(product, len(variants)),
            "variants": [_variant_summary(v) for v in variants],
            "total_stock": sum(int(v.stock) for v in variants),
            **money_envelope(),
        }


async def check_product_inventory(
    product_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Current stock and availability for a product and its variants."""
    result = await check_stock(product_id, ctx=ctx, token=token)
    if result.get("success") is not True or "variants" not in result:
        if result.get("success") is True:
            result = {
                "success": True,
                "product_id": result["variant"].get("id"),
                "product_name": result.get("product_name"),
                "variants": [result["variant"]],
                "total_stock": result["variant"].get("stock", 0),
                **money_envelope(),
                **{
                    k: result[k]
                    for k in ("match", "matched_on")
                    if k in result
                },
            }
        else:
            return result
    result["availability"] = (
        "in_stock" if result["total_stock"] > 0 else "out_of_stock"
    )
    return result


async def list_low_stock_products(
    threshold: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Variants at or below `threshold` stock (DB filter/paginate, bounded).

    No low-stock threshold exists in the codebase, so the caller supplies
    one per call (default 5); filtering, counting, and limiting all happen
    in PostgreSQL.
    """
    try:
        require_mcp_perm(ctx, token, PRODUCTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    try:
        eff_threshold = DEFAULT_LOW_STOCK_THRESHOLD if threshold is None else int(threshold)
    except (TypeError, ValueError):
        return {"success": False, "error": "threshold must be an integer"}
    if eff_threshold < 0:
        return {"success": False, "error": "threshold must be zero or positive"}
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
        base = select(ProductVariant).where(ProductVariant.stock <= eff_threshold)
        total = session.execute(
            select(func.count()).select_from(base.subquery())
        ).scalar() or 0
        rows = session.execute(
            base.options(selectinload(ProductVariant.product))
            .order_by(ProductVariant.stock.asc(), ProductVariant.sku.asc())
            .offset(eff_offset)
            .limit(eff_limit)
        ).scalars().all()
        items = [
            {
                **_variant_summary(v),
                "product_id": str(v.product_id),
                "product_name": v.product.name if v.product else None,
            }
            for v in rows
        ]
    return {
        "success": True,
        "variants": items,
        "returned_count": len(items),
        "total_matching": total,
        "threshold": eff_threshold,
        "limit": eff_limit,
        "offset": eff_offset,
        **money_envelope(),
    }


async def adjust_stock(
    variant_id: str | int | None = None,
    delta: Any = None,
    reason: str | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then apply a signed stock delta (two-step, confirmed only).

    Absolute overwrites are refused: only relative adjustments with a
    reason. Execution re-locks the variant row, re-checks the fingerprint
    (concurrent adjustments fail closed), floors at zero, and audits
    before/after. No RAG sync: stock is not catalog text.

    Permission mirrors the UI: stock lives on the variant edited via
    products.update, so that key (or the specialist inventory.adjust)
    grants access — revoking both blocks page and agent together.
    """
    try:
        user_info, _ = require_mcp_perm_any(ctx, token, PRODUCTS_UPDATE, INVENTORY_ADJUST)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if variant_id is None:
        return {"success": False, "error": "variant_id is required"}
    ref = str(variant_id).strip()
    if not ref:
        return {"success": False, "error": "variant_id is required"}
    try:
        delta_int = int(delta)
    except (TypeError, ValueError):
        return {"success": False, "error": "delta must be a non-zero integer"}
    if delta_int == 0:
        return {"success": False, "error": "delta must be a non-zero integer"}
    text_reason = (reason or "").strip()
    if not text_reason:
        return {"success": False, "error": "reason is required"}
    if len(text_reason) > 500:
        return {"success": False, "error": "reason must be at most 500 characters"}

    user_id = parse_user_id(user_info)
    if user_id is None:
        return {"success": False, "error": "Could not validate credentials"}
    changes = {"delta": delta_int, "reason": text_reason}

    with Session(engine) as session:
        variant = _resolve_variant(session, ref)
        if variant is None:
            return {"success": False, "error": f"Variant {ref} not found"}
        fingerprint = {"stock": int(variant.stock)}
        if not confirmed:
            preview_stock = int(variant.stock) + delta_int
            if preview_stock < 0:
                return {
                    "success": False,
                    "error": f"Adjustment refused: stock would go negative ({variant.stock} + {delta_int})",
                }
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": issue_write_preview(
                    user_id, "stock_adjust", str(variant.id), changes, fingerprint),
                "expires_in_minutes": WRITE_PREVIEW_TTL_MINUTES,
                "variant": _variant_summary(variant),
                "delta": delta_int,
                "resulting_stock": preview_stock,
                "reason": text_reason,
                **money_envelope(),
            }

        problem = verify_write_preview(
            preview_token, user_id, "stock_adjust", str(variant.id), changes, fingerprint)
        if isinstance(problem, str):
            return {"success": False, "error": problem}

        locked = session.execute(
            select(ProductVariant).where(ProductVariant.id == variant.id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            return {"success": False, "error": f"Variant {ref} not found"}
        if int(locked.stock) != fingerprint["stock"]:
            return {
                "success": False,
                "error": "Preview is stale (stock changed since preview); request a new preview",
            }
        new_stock = int(locked.stock) + delta_int
        if new_stock < 0:
            return {
                "success": False,
                "error": f"Adjustment refused: stock would go negative ({locked.stock} + {delta_int})",
            }
        before = int(locked.stock)
        locked.stock = new_stock
        session.add(locked)
        session.commit()
        session.refresh(locked)
        audit_repo.log_and_commit(
            session, action="product.updated", entity="product_variant",
            entity_id=locked.id, actor_id=user_id,
            before={"stock": before, "reason": text_reason},
            after={"stock": new_stock},
        )
        return {
            "success": True,
            "adjusted": True,
            "variant": _variant_summary(locked),
            "delta": delta_int,
            "previous_stock": before,
            **money_envelope(),
        }
