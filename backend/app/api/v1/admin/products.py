from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.api.deps import SessionDep, require_perm
from app.models.product import Product
from app.models.user import User
from app.repositories import product as product_repo
from app.repositories import audit as audit_repo
from app.schemas.product import ProductRead

router = APIRouter(prefix="/admin/products", tags=["Admin Products"])


@router.get("", response_model=dict)
def get_all_products_admin(
    session: SessionDep,
    current_user: User = Depends(require_perm("products.view")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    search: str | None = None,
    is_active: bool | None = None,
    category_id: UUID | None = None,
):
    """
    Get all products with pagination (Admin only).
    """
    skip = (page - 1) * limit

    products, total = product_repo.get_all_products_admin(
        session=session,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        category_id=category_id,
    )

    # Explicit mapping (same as /export below): response_model=dict
    # serializes bare SQLModel via .dict(), which drops relationships —
    # without this, `images`/`variants` never reach the admin UI.
    items = [
        {
            "id": str(product.id),
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "price": str(product.price),
            "compare_at_price": str(product.compare_at_price) if product.compare_at_price else None,
            "is_active": product.is_active,
            "created_at": product.created_at.isoformat() if product.created_at else None,
            "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            "images": [
                {
                    "id": str(img.id),
                    "url": img.url,
                    "secure_url": img.secure_url,
                    "alt_text": img.alt_text,
                    "sort_order": img.sort_order,
                }
                for img in product.images
            ],
            "variants": [{"id": str(v.id)} for v in product.variants],
        }
        for product in products
    ]

    return {
        "products": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
        }
    }


# 👇 MOVED /export HERE - BEFORE /{product_id}
@router.get("/export", response_model=dict)
def export_products(
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("products.export")),
    format: str = Query(default="json"),
):
    """
    Export products data (Admin only).
    """
    # Load products with images and variants
    statement = select(Product).options(
        selectinload(Product.images),
        selectinload(Product.variants)
    )
    products = session.exec(statement).all()
    
    export_data = []
    for product in products:
        export_data.append({
            "id": str(product.id),
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "price": str(product.price),
            "compare_at_price": str(product.compare_at_price) if product.compare_at_price else None,
            "is_active": product.is_active,
            "created_at": product.created_at.isoformat(),
            "updated_at": product.updated_at.isoformat(),
            "images": [
                {
                    "id": str(img.id),
                    "url": img.url,
                    "alt_text": img.alt_text,
                    "sort_order": img.sort_order,
                    "created_at": img.created_at.isoformat(),
                }
                for img in product.images
            ],
            "variants": [
                {
                    "id": str(v.id),
                    "product_id": str(v.product_id),
                    "sku": v.sku,
                    "attributes": v.attributes,
                    "price_override": str(v.price_override) if v.price_override else None,
                    "stock": v.stock,
                    "created_at": v.created_at.isoformat(),
                }
                for v in product.variants
            ],
        })
    
    audit_repo.log_and_commit(
        session, action="product.exported", entity="product",
        entity_id=None, actor_id=current_user.id,
        after={"format": format, "count": len(export_data)},
        ip_address=audit_repo.client_ip(request),
    )
    return {
        "format": format,
        "count": len(export_data),
        "data": export_data
    }


# 👇 /{product_id} comes AFTER /export
@router.get("/by-slug/{slug}", response_model=ProductRead)
def get_product_admin_by_slug(
    slug: str,
    session: SessionDep,
    current_user: User = Depends(require_perm("products.view")),
):
    """
    Get product by slug (Admin only). Unlike the public endpoint,
    inactive products are included so they can be viewed/edited.
    """
    product = product_repo.get_product_by_slug(session, slug)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product_admin(
    product_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("products.view")),
):
    """
    Get product by ID (Admin only).
    """
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    return product


@router.post("/bulk-delete", response_model=dict)
def bulk_delete_products(
    product_ids: list[UUID],
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("products.delete")),
):
    """
    Hard-delete products (requires products.delete permission).

    Products with order history are blocked (409) — financial records
    must survive. Use deactivate for those instead.
    """
    from app.services.cloudinary_service import delete_image as delete_cloudinary_image
    from app.services.rag_service import delete_product_from_rag

    if not product_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No product IDs provided"
        )

    result = product_repo.bulk_delete_products(session, product_ids, commit=False)
    deleted = result["deleted"]
    blocked = result["blocked"]

    if not deleted:
        # Nothing deletable — surface the guard reason (e.g. single-row
        # UI shows "… has order history" instead of a generic failure).
        reason = blocked[0]["reason"] if blocked else "unknown"
        name = blocked[0]["name"] if blocked else "product"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Cannot delete "{name}": {reason}. Deactivate it instead.',
        )

    audit_repo.log_and_commit(
        session, action="product.bulk_deleted", entity="product",
        entity_id=None, actor_id=current_user.id,
        after={"ids": [str(i) for i in product_ids],
               "hard": True, "deleted_count": len(deleted),
               "blocked": blocked},
        ip_address=audit_repo.client_ip(request),
    )

    # External cleanup after commit (best-effort, mirrors review delete).
    for public_id in result["cloudinary_public_ids"]:
        try:
            delete_cloudinary_image(public_id)
        except Exception as exc:
            print(f"⚠️ Cloudinary cleanup failed for {public_id}: {exc}")
    for pid in result["rag_product_ids"]:
        try:
            delete_product_from_rag(pid)
        except Exception as exc:
            print(f"⚠️ RAG cleanup failed for {pid}: {exc}")

    message = f"Successfully deleted {len(deleted)} product(s)"
    if blocked:
        names = ", ".join(f'"{b["name"]}"' for b in blocked)
        message += f"; skipped {len(blocked)} with order history: {names}"
    return {
        "deleted_count": len(deleted),
        "deleted": deleted,
        "blocked": blocked,
        "message": message,
    }


@router.post("/bulk-update-status", response_model=dict)
def bulk_update_product_status(
    product_ids: list[UUID],
    is_active: bool,
    session: SessionDep,
    request: Request,
    # Bulk status flips use the same grant as single-product updates
    # (legacy code restricted this to admin; managers/staff could already
    # flip products one by one, so products.update is the honest mapping).
    current_user: User = Depends(require_perm("products.update")),
):
    """
    Bulk update product status (Admin only).
    """
    if not product_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No product IDs provided"
        )
    
    updated_count = product_repo.bulk_update_product_status(session, product_ids, is_active, commit=False)
    audit_repo.log_and_commit(
        session, action="product.bulk_status", entity="product",
        entity_id=None, actor_id=current_user.id,
        after={"ids": [str(i) for i in product_ids],
               "is_active": is_active, "updated_count": updated_count},
        ip_address=audit_repo.client_ip(request),
    )
    
    return {
        "updated_count": updated_count,
        "message": f"Successfully updated {updated_count} products to {'active' if is_active else 'inactive'}"
    }
