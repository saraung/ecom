"""MCP product tools (PostgreSQL reads + confirmed writes).

Reads reuse repositories/product.py and utils/pricing.py. Writes preview
first (signed token binding user + target + exact changes + live-state
fingerprint) and execute only with confirmed=true, re-resolving the
caller, re-checking the permission, re-locking the row, and re-validating
everything before the canonical repo functions commit. Product edits
trigger the existing non-fatal RAG re-index hook like the REST routes.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from app.db.database import engine
from app.mcp.tools import money_envelope
from app.models.category import Category
from app.models.product import Product, ProductVariant
from app.mcp.auth import MCPAuthError, parse_user_id
from app.mcp.guards import (
    MCPForbiddenError,
    PRODUCTS_DELETE,
    PRODUCTS_MANAGE_PRICES,
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
from app.schemas.product import ProductUpdate
from app.utils.pricing import get_effective_price

try:
    from mcp.server.mcpserver.context import Context
except Exception:  # pragma: no cover - type-checking fallback
    Context = Any  # type: ignore[no-redef,misc]


DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50
MAX_COMPARE = 5

# update_product allowlist: price/slug changes go through the dedicated
# price tool / REST routes, never silently alongside other edits.
UPDATE_ALLOWLIST = ("name", "description", "category_id", "is_active")


def _primary_image_url(product) -> str | None:
    """First product image URL (front-of-catalog), secure URL preferred."""
    try:
        images = sorted(product.images or [], key=lambda i: (i.sort_order or 0))
    except Exception:
        return None
    for img in images:
        url = getattr(img, "secure_url", None) or getattr(img, "url", None)
        if url:
            return url
    return None


def _product_summary(product: Product, variant_count: int | None = None) -> dict:
    return {
        "id": str(product.id),
        "name": product.name,
        "slug": product.slug,
        "price": str(product.price),
        "compare_at_price": str(product.compare_at_price) if product.compare_at_price is not None else None,
        "is_active": bool(product.is_active),
        "category_id": str(product.category_id) if product.category_id else None,
        "variant_count": variant_count,
        "image_url": _primary_image_url(product),
    }


def _variant_summary(variant: ProductVariant) -> dict:
    return {
        "id": str(variant.id),
        "sku": variant.sku,
        "attributes": dict(variant.attributes or {}),
        "price_override": str(variant.price_override) if variant.price_override is not None else None,
        "effective_price": str(get_effective_price(variant.product, variant)),
        "stock": int(variant.stock),
    }


def _resolve_product(session: Session, ref: str):
    """Product by UUID, then slug, then via variant SKU (None when unknown)."""
    try:
        product_uuid = uuid.UUID(ref)
    except (ValueError, AttributeError, TypeError):
        product_uuid = None
    if product_uuid is not None:
        product = product_repo.get_product_by_id(session, product_uuid)
        if product is not None:
            return product
    product = product_repo.get_product_by_slug(session, ref)
    if product is not None:
        return product
    variant = product_repo.get_variant_by_sku(session, ref)
    return variant.product if variant is not None else None


def _resolve_variant(session: Session, ref: str):
    """Variant by UUID, then SKU (None when unknown)."""
    try:
        variant_uuid = uuid.UUID(ref)
    except (ValueError, AttributeError, TypeError):
        variant_uuid = None
    if variant_uuid is not None:
        variant = product_repo.get_variant_by_id(session, variant_uuid)
        if variant is not None:
            return variant
    return product_repo.get_variant_by_sku(session, ref)


def _require_user(user_info: dict) -> UUID | str:
    user_id = parse_user_id(user_info)
    if user_id is None:
        return "Could not validate credentials"
    return user_id


async def list_products(
    search: str | None = None,
    is_active: bool | None = None,
    limit: int | None = None,
    offset: int | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """List product summaries (PostgreSQL filter/sort/paginate, bounded page).

    sort_by is name | price | created_at, sort_dir asc | desc — sorting
    happens in PostgreSQL, so cheapest/most-expensive questions need one
    call (e.g. sort_by=price, sort_dir=asc, limit=1), never a page scan.
    A product card renders automatically from returned product data —
    describe in text, never paste image URLs or markdown images yourself.
    Always call a product tool before describing any product, even when
    details are already in context, so the card renders every time.
    """
    try:
        require_mcp_perm(ctx, token, PRODUCTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

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

    norm_sort = (sort_by or "created_at").strip().lower()
    if norm_sort not in ("name", "price", "created_at"):
        return {"success": False, "error": "sort_by must be one of: name, price, created_at"}
    norm_dir = (sort_dir or "desc").strip().lower()
    if norm_dir not in ("asc", "desc"):
        return {"success": False, "error": "sort_dir must be 'asc' or 'desc'"}

    with Session(engine) as session:
        try:
            products, total = product_repo.get_all_products_admin(
                session, skip=eff_offset, limit=eff_limit,
                search=(search or None), is_active=is_active,
                sort_by=norm_sort, sort_dir=norm_dir,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        items = [
            _product_summary(p, len(p.variants or [])) for p in products
        ]
    return {
        "success": True,
        "products": items,
        "returned_count": len(items),
        "total_matching": total,
        "limit": eff_limit,
        "offset": eff_offset,
        "sort_by": norm_sort,
        "sort_dir": norm_dir,
        **money_envelope(),
    }


async def get_product(
    product_id: str | int | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Product detail by UUID, slug, or variant SKU (read-only).

    A product card renders automatically from the returned product —
    describe in text, never paste image URLs or markdown images yourself.
    Always call this tool before describing any product, even when details
    are already in context, so the card renders every time.
    """
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
        product = _resolve_product(session, ref)
        if product is None:
            return {"success": False, "error": f"Product {ref} not found"}
        variants = product_repo.get_variants(session, product.id)
        return {
            "success": True,
            "product": {
                **_product_summary(product, len(variants)),
                "description": product.description,
                "variants": [_variant_summary(v) for v in variants],
            },
            **money_envelope(),
        }


async def compare_products(
    product_ids: list | None = None,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Side-by-side price/attribute comparison for up to MAX_COMPARE products."""
    try:
        require_mcp_perm(ctx, token, PRODUCTS_VIEW)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if not isinstance(product_ids, list) or not product_ids:
        return {"success": False, "error": "product_ids must be a non-empty list"}
    if len(product_ids) > MAX_COMPARE:
        return {"success": False, "error": f"Compare at most {MAX_COMPARE} products at once"}

    with Session(engine) as session:
        rows = []
        for raw in product_ids:
            ref = str(raw).strip() if raw is not None else ""
            if not ref:
                return {"success": False, "error": "product_ids must not contain blanks"}
            product = _resolve_product(session, ref)
            if product is None:
                return {"success": False, "error": f"Product {ref} not found"}
            variants = product_repo.get_variants(session, product.id)
            rows.append(
                {
                    **_product_summary(product, len(variants)),
                    "variant_skus": [v.sku for v in variants],
                }
            )
    return {
        "success": True,
        "products": rows,
        "compared_count": len(rows),
        **money_envelope(),
    }


def _validate_changes(raw: Any) -> dict | str:
    """Allowlist + type/length validation for update_product (no prices/slug)."""
    if not isinstance(raw, dict) or not raw:
        return "changes must be a non-empty object"
    unknown = [k for k in raw if k not in UPDATE_ALLOWLIST]
    if unknown:
        return (
            f"Unsupported fields: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(UPDATE_ALLOWLIST)} (prices via update_product_price)"
        )
    changes: dict[str, Any] = {}
    if "name" in raw:
        name = str(raw["name"]).strip()
        if not (1 <= len(name) <= 150):
            return "name must be 1..150 characters"
        changes["name"] = name
    if "description" in raw:
        changes["description"] = None if raw["description"] is None else str(raw["description"])
    if "category_id" in raw:
        if raw["category_id"] is None:
            changes["category_id"] = None
        else:
            try:
                changes["category_id"] = uuid.UUID(str(raw["category_id"]))
            except (ValueError, AttributeError, TypeError):
                return "category_id must be a UUID or null"
    if "is_active" in raw:
        if not isinstance(raw["is_active"], bool):
            return "is_active must be true or false"
        changes["is_active"] = raw["is_active"]
    return changes


async def update_product(
    product_id: str | int | None = None,
    changes: dict | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then apply a product edit (two-step, confirmed only)."""
    try:
        user_info, _ = require_mcp_perm(ctx, token, PRODUCTS_UPDATE)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if product_id is None:
        return {"success": False, "error": "product_id is required"}
    ref = str(product_id).strip()
    if not ref:
        return {"success": False, "error": "product_id is required"}
    validated = _validate_changes(changes)
    if isinstance(validated, str):
        return {"success": False, "error": validated}

    user_id = _require_user(user_info)
    if isinstance(user_id, str):
        return {"success": False, "error": user_id}

    with Session(engine) as session:
        product = _resolve_product(session, ref)
        if product is None:
            return {"success": False, "error": f"Product {ref} not found"}
        if validated.get("category_id") is not None and session.get(
            Category, validated["category_id"]
        ) is None:
            return {"success": False, "error": "category_id does not exist"}
        fingerprint = {
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            "current": {k: str(getattr(product, k)) for k in validated},
        }
        if not confirmed:
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": issue_write_preview(
                    user_id, "product_update", str(product.id), validated, fingerprint),
                "expires_in_minutes": 10,
                "product": _product_summary(product, None),
                "changes": {k: (str(v) if not isinstance(v, bool) else v) for k, v in validated.items()},
                **money_envelope(),
            }

        problem = verify_write_preview(
            preview_token, user_id, "product_update", str(product.id), validated, fingerprint)
        if isinstance(problem, str):
            return {"success": False, "error": problem}

        locked = session.execute(
            select(Product).where(Product.id == product.id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            return {"success": False, "error": f"Product {ref} not found"}
        if validated.get("category_id") is not None and session.get(
            Category, validated["category_id"]
        ) is None:
            return {"success": False, "error": "category_id does not exist"}
        before = {k: str(getattr(locked, k)) for k in validated}
        updated = product_repo.update_product(session, locked, ProductUpdate(**validated))
        session.commit()
        session.refresh(updated)
        audit_repo.log_and_commit(
            session, action="product.updated", entity="product",
            entity_id=updated.id, actor_id=user_id,
            before=before,
            after={k: str(getattr(updated, k)) for k in validated},
        )
        try:
            from app.services.rag_service import ingest_all_products

            ingest_all_products(session)
        except Exception as e:
            print(f"⚠️ MCP product update RAG sync failed: {e}")
        return {
            "success": True,
            "updated": True,
            "product": _product_summary(updated, None),
            **money_envelope(),
        }


def _parse_price(value, field: str) -> Decimal | str:
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return f"{field} must be a positive number"
    if amount <= 0:
        return f"{field} must be a positive number"
    return amount.quantize(Decimal("0.01"))


async def update_product_price(
    product_id: str | int | None = None,
    price: Any = None,
    compare_at_price: Any = None,
    variant_id: str | int | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then change a product price or variant override (two-step).

    Permission mirrors the UI: prices are edited through the product
    endpoints via products.update, so that key (or the specialist
    products.manage_prices) grants access.
    """
    try:
        user_info, _ = require_mcp_perm_any(ctx, token, PRODUCTS_UPDATE, PRODUCTS_MANAGE_PRICES)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if product_id is None:
        return {"success": False, "error": "product_id is required"}
    ref = str(product_id).strip()
    if not ref:
        return {"success": False, "error": "product_id is required"}
    if price is None and compare_at_price is None:
        return {"success": False, "error": "Provide price and/or compare_at_price"}

    changes: dict[str, Any] = {}
    for field, value in (("price", price), ("compare_at_price", compare_at_price)):
        if value is None:
            continue
        parsed = _parse_price(value, field)
        if isinstance(parsed, str):
            return {"success": False, "error": parsed}
        changes[field] = str(parsed)

    user_id = _require_user(user_info)
    if isinstance(user_id, str):
        return {"success": False, "error": user_id}

    with Session(engine) as session:
        product = _resolve_product(session, ref)
        if product is None:
            return {"success": False, "error": f"Product {ref} not found"}
        variant = None
        if variant_id is not None:
            variant = _resolve_variant(session, str(variant_id).strip())
            if variant is None or variant.product_id != product.id:
                return {"success": False, "error": f"Variant {variant_id} not found on this product"}
            if "price" in changes:
                changes = {"price_override": changes["price"]}
                if "compare_at_price" in changes:
                    return {"success": False, "error": "compare_at_price applies to products, not variants"}
        target = variant or product
        kind = "variant_price" if variant is not None else "product_price"
        fingerprint = {
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            "current": {k: str(getattr(target, k)) for k in changes},
        }
        if not confirmed:
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": issue_write_preview(
                    user_id, kind, str(target.id), changes, fingerprint),
                "expires_in_minutes": 10,
                "product": _product_summary(product, None),
                "variant": {"id": str(variant.id), "sku": variant.sku} if variant else None,
                "changes": changes,
                **money_envelope(),
            }

        problem = verify_write_preview(
            preview_token, user_id, kind, str(target.id), changes, fingerprint)
        if isinstance(problem, str):
            return {"success": False, "error": problem}

        model = ProductVariant if variant is not None else Product
        locked = session.execute(
            select(model).where(model.id == target.id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            return {"success": False, "error": "Target not found"}
        before = {k: str(getattr(locked, k)) for k in changes}
        for field, raw in changes.items():
            setattr(locked, field, Decimal(raw))
        session.add(locked)
        session.commit()
        session.refresh(locked)
        audit_repo.log_and_commit(
            session, action="product.updated", entity="product",
            entity_id=product.id, actor_id=user_id,
            before=before,
            after={k: str(getattr(locked, k)) for k in changes},
        )
        try:
            from app.services.rag_service import ingest_all_products

            ingest_all_products(session)
        except Exception as e:
            print(f"⚠️ MCP price update RAG sync failed: {e}")
        return {
            "success": True,
            "updated": True,
            "product": _product_summary(product, None),
            "variant": {"id": str(locked.id), "sku": locked.sku} if variant else None,
            "changes": changes,
            **money_envelope(),
        }


async def delete_product(
    product_id: str | int | None = None,
    preview_token: str | None = None,
    confirmed: bool = False,
    ctx: Context | None = None,
    token: str | None = None,
) -> dict:
    """Preview then soft-deactivate a product (two-step; never hard-delete).

    Mirrors DELETE /products/{id}: is_active=False + product.deleted audit.
    Referenced rows are safe because nothing is physically removed.
    """
    try:
        user_info, _ = require_mcp_perm(ctx, token, PRODUCTS_DELETE)
    except MCPAuthError as exc:
        return exc.to_dict()
    except MCPForbiddenError as exc:
        return exc.to_dict()

    if product_id is None:
        return {"success": False, "error": "product_id is required"}
    ref = str(product_id).strip()
    if not ref:
        return {"success": False, "error": "product_id is required"}

    user_id = _require_user(user_info)
    if isinstance(user_id, str):
        return {"success": False, "error": user_id}

    with Session(engine) as session:
        product = _resolve_product(session, ref)
        if product is None:
            return {"success": False, "error": f"Product {ref} not found"}
        fingerprint = {
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            "is_active": bool(product.is_active),
        }
        if not confirmed:
            if not product.is_active:
                return {"success": False, "error": "Product is already deactivated"}
            return {
                "success": True,
                "requires_confirmation": True,
                "preview_token": issue_write_preview(
                    user_id, "product_delete", str(product.id), {}, fingerprint),
                "expires_in_minutes": 10,
                "product": _product_summary(product, None),
                "consequence": "Deactivates the product (hidden from catalog). Nothing is physically deleted.",
                **money_envelope(),
            }

        problem = verify_write_preview(
            preview_token, user_id, "product_delete", str(product.id), {}, fingerprint)
        if isinstance(problem, str):
            return {"success": False, "error": problem}

        locked = session.execute(
            select(Product).where(Product.id == product.id).with_for_update()
        ).scalar_one_or_none()
        if locked is None:
            return {"success": False, "error": f"Product {ref} not found"}
        if not locked.is_active:
            return {"success": False, "error": "Product is already deactivated"}
        snapshot = {"name": locked.name, "slug": locked.slug, "price": str(locked.price)}
        product_repo.delete_product(session, locked, commit=False)
        audit_repo.log_and_commit(
            session, action="product.deleted", entity="product",
            entity_id=locked.id, actor_id=user_id, before=snapshot,
        )
        try:
            from app.services.rag_service import delete_product_from_rag

            delete_product_from_rag(product.id)
        except Exception as e:
            print(f"⚠️ MCP product delete RAG removal failed: {e}")
        return {
            "success": True,
            "deleted": True,
            "product": _product_summary(locked, None),
            **money_envelope(),
        }
