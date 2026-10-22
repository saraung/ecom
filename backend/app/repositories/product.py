from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlmodel import Session

from app.models.product import Product, ProductVariant
from app.models.review import Review
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)


def _catalog_query(session, search=None, category_id=None, min_price=None, max_price=None, include_descendants=False):
    from app.models.category import Category
    statement = select(Product).where(Product.is_active == True)
    if search and search.strip():
        term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        statement = statement.where(Product.name.ilike(pattern, escape="\\") |
                                    Product.slug.ilike(pattern, escape="\\") |
                                    Product.description.ilike(pattern, escape="\\"))
    if category_id:
        ids = {category_id}
        if include_descendants:
            categories = session.execute(select(Category.id, Category.parent_id)).all()
            while True:
                children = {cid for cid, parent in categories if parent in ids} - ids
                if not children:
                    break
                ids.update(children)
        statement = statement.where(Product.category_id.in_(ids))
    if min_price is not None:
        statement = statement.where(Product.price >= min_price)
    if max_price is not None:
        statement = statement.where(Product.price <= max_price)
    return statement


def count_catalog_products(session, **filters):
    return session.execute(select(func.count()).select_from(_catalog_query(session, **filters).subquery())).scalar_one()


def get_products(
    session: Session,
    search: str | None = None,
    category_id: UUID | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    sort: str = "newest",
    skip: int = 0,
    limit: int = 20,
    include_descendants: bool = False,
) -> list[Product]:
    statement = _catalog_query(session, search, category_id, min_price, max_price, include_descendants).options(
        selectinload(Product.variants), selectinload(Product.images))

    if sort == "price_asc":
        statement = statement.order_by(Product.price.asc())
    elif sort == "price_desc":
        statement = statement.order_by(Product.price.desc())
    elif sort == "name_asc":
        statement = statement.order_by(Product.name.asc())
    elif sort == "name_desc":
        statement = statement.order_by(Product.name.desc())
    elif sort == "oldest":
        statement = statement.order_by(Product.created_at.asc())
    else:
        statement = statement.order_by(Product.created_at.desc())

    statement = statement.order_by(Product.id.asc()).offset(skip).limit(limit)

    result = session.execute(statement)
    return result.scalars().all()


def get_product_by_id(
    session: Session,
    product_id: UUID,
) -> Product | None:

    statement = (
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.variants),
            selectinload(Product.images)
        )
    )

    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_product_by_slug(
    session: Session,
    slug: str,
) -> Product | None:

    statement = (
        select(Product)
        .where(Product.slug == slug)
        .options(
            selectinload(Product.variants),
            selectinload(Product.images)
        )
    )

    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_product_rating_stats(
    session: Session,
    product_ids: list[UUID],
) -> dict[UUID, dict]:
    """
    Batch-fetch average rating + review count for a set of products in a
    single grouped query, instead of one query per product (avoids N+1
    when populating a product list response).

    Returns a dict keyed by product_id: {"average_rating": float, "review_count": int}.
    Products with no reviews simply won't have an entry — callers should
    default to {"average_rating": 0.0, "review_count": 0}.
    Hidden (moderated) reviews are excluded, matching the storefront paths.
    """
    if not product_ids:
        return {}

    statement = (
        select(
            Review.product_id,
            func.avg(Review.rating).label("average_rating"),
            func.count(Review.id).label("review_count"),
        )
        .where(Review.product_id.in_(product_ids), Review.is_hidden == False)  # noqa: E712
        .group_by(Review.product_id)
    )

    result = session.execute(statement)

    stats: dict[UUID, dict] = {}
    for product_id, avg_rating, count in result:
        stats[product_id] = {
            "average_rating": round(float(avg_rating), 1) if avg_rating is not None else 0.0,
            "review_count": count or 0,
        }

    return stats


def create_product(
    session: Session,
    product_data: ProductCreate,
    created_by: UUID,
    *, commit: bool = True,
) -> Product:

    product = Product(
        **product_data.model_dump(),
        created_by=created_by,
    )

    session.add(product)
    if commit:
        session.commit()
        session.refresh(product)
    else:
        session.flush()

    return product


def update_product(
    session: Session,
    product: Product,
    product_data: ProductUpdate,
    *, commit: bool = True,
) -> Product:

    update_data = product_data.model_dump(
        exclude_unset=True
    )

    for field, value in update_data.items():
        setattr(
            product,
            field,
            value,
        )

    session.add(product)
    if commit:
        session.commit()
        session.refresh(product)
    else:
        session.flush()

    return product


def delete_product(
    session: Session,
    product: Product,
    *, commit: bool = True,
) -> None:

    # Soft delete.
    product.is_active = False

    session.add(product)
    session.commit() if commit else session.flush()


# =========================================================
# VARIANTS
# =========================================================

def get_variants(
    session: Session,
    product_id: UUID,
) -> list[ProductVariant]:

    statement = select(ProductVariant).where(
        ProductVariant.product_id == product_id
    )

    result = session.execute(statement)
    return result.scalars().all()


def get_variant_by_id(
    session: Session,
    variant_id: UUID,
) -> ProductVariant | None:

    return session.get(
        ProductVariant,
        variant_id,
    )


def get_variant_by_sku(
    session: Session,
    sku: str,
) -> ProductVariant | None:

    statement = select(ProductVariant).where(
        ProductVariant.sku == sku
    )

    result = session.execute(statement)
    return result.scalar_one_or_none()


def create_variant(
    session: Session,
    product_id: UUID,
    variant_data: ProductVariantCreate,
) -> ProductVariant:

    variant = ProductVariant(
        product_id=product_id,
        **variant_data.model_dump(),
    )

    session.add(variant)
    session.commit()
    session.refresh(variant)

    return variant


def update_variant(
    session: Session,
    variant: ProductVariant,
    variant_data: ProductVariantUpdate,
) -> ProductVariant:

    update_data = variant_data.model_dump(
        exclude_unset=True
    )

    for field, value in update_data.items():
        setattr(
            variant,
            field,
            value,
        )

    session.add(variant)
    session.commit()
    session.refresh(variant)

    return variant


# =========================================================
# VARIANTS - DELETE  ⬅️ NEW FUNCTION
# =========================================================

def delete_variant(
    session: Session,
    variant: ProductVariant,
) -> None:
    """
    Delete a product variant (hard delete).
    """
    session.delete(variant)
    session.commit()


# =========================================================
# ADMIN FUNCTIONS
# =========================================================

def get_total_products(session: Session) -> int:
    """Get total number of products"""
    statement = select(func.count(Product.id))
    result = session.execute(statement)
    return result.scalar() or 0


def get_all_products(session: Session) -> list[Product]:
    """Get all products (for export)"""
    statement = select(Product).options(
        selectinload(Product.images),
        selectinload(Product.variants)
    ).order_by(Product.created_at.desc())
    result = session.execute(statement)
    return result.scalars().all()


#: Allowed sort keys for get_all_products_admin (column whitelist — the
#: sort key is never interpolated raw, so arbitrary column access is out).
PRODUCT_ADMIN_SORTS = {
    "name": "name",
    "price": "price",
    "created_at": "created_at",
}


def get_all_products_admin(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    is_active: bool | None = None,
    category_id: UUID | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
) -> tuple[list[Product], int]:
    """
    Get all products with filters (Admin only).
    Includes inactive products.
    sort_by is one of name | price | created_at (default created_at);
    sort_dir is asc | desc (default desc). Unknown values raise ValueError
    so callers surface a clean validation error instead of SQL text.
    """
    key = PRODUCT_ADMIN_SORTS.get((sort_by or "").strip().lower())
    if key is None:
        raise ValueError(f"sort_by must be one of: {', '.join(sorted(PRODUCT_ADMIN_SORTS))}")
    direction = (sort_dir or "").strip().lower()
    if direction not in ("asc", "desc"):
        raise ValueError("sort_dir must be 'asc' or 'desc'")
    statement = select(Product).options(
        selectinload(Product.variants),
        selectinload(Product.images)
    )
    
    if search:
        statement = statement.where(
            (Product.name.ilike(f"%{search}%")) |
            (Product.slug.ilike(f"%{search}%"))
        )
    
    if is_active is not None:
        statement = statement.where(Product.is_active == is_active)

    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    
    # Get total count
    count_statement = select(func.count()).select_from(statement.subquery())
    result = session.execute(count_statement)
    total = result.scalar() or 0

    column = getattr(Product, key)
    ordering = column.asc() if direction == "asc" else column.desc()
    statement = (
        statement.order_by(ordering, Product.id.asc()).offset(skip).limit(limit)
    )
    result = session.execute(statement)
    products = result.scalars().all()
    
    return products, total


def bulk_delete_products(session: Session, product_ids: list[UUID], *, commit: bool = True) -> dict:
    """Hard-delete products with dependent cleanup.

    - BLOCKED (order history): products whose variants appear in any
      order_items are never deleted — financial records must survive.
    - Otherwise removes: cart items, wishlist entries, reviews (+ their
      images), product images, variants, then the product row itself.
    - External side effects (Cloudinary, RAG) are NOT done here — the
      caller receives `cloudinary_public_ids` / `rag_product_ids` and
      cleans those up after commit (same pattern as admin review delete).

    Returns {"deleted": [id-str], "blocked": [{"id", "name", "reason"}],
             "cloudinary_public_ids": [...], "rag_product_ids": [...]}.
    """
    from app.models.cart import CartItem
    from app.models.order import OrderItem
    from app.models.product_image import ProductImage
    from app.models.review import Review
    from app.models.review_image import ReviewImage
    from app.models.wishlist import Wishlist

    if not product_ids:
        return {"deleted": [], "blocked": [],
                "cloudinary_public_ids": [], "rag_product_ids": []}

    statement = (
        select(Product)
        .where(Product.id.in_(product_ids))
        .options(
            selectinload(Product.images),
            selectinload(Product.variants),
        )
    )
    products = session.execute(statement).scalars().all()

    deleted: list[str] = []
    blocked: list[dict] = []
    cloudinary_public_ids: list[str] = []
    rag_product_ids: list[str] = []

    for product in products:
        variant_ids = [v.id for v in product.variants]

        # Financial history guard: never hard-delete an ordered product.
        has_orders = False
        if variant_ids:
            has_orders = session.execute(
                select(OrderItem.id).where(
                    OrderItem.variant_id.in_(variant_ids)
                ).limit(1)
            ).first() is not None
        if has_orders:
            blocked.append({
                "id": str(product.id),
                "name": product.name,
                "reason": "has order history",
            })
            continue

        # Transient dependents: cart items + wishlist entries.
        if variant_ids:
            for item in session.execute(
                select(CartItem).where(
                    CartItem.variant_id.in_(variant_ids)
                )
            ).scalars().all():
                session.delete(item)
        for entry in session.execute(
            select(Wishlist).where(Wishlist.product_id == product.id)
        ).scalars().all():
            session.delete(entry)

        # Reviews (+ their images) are product-scoped: removed with it.
        for review in session.execute(
            select(Review).where(Review.product_id == product.id)
        ).scalars().all():
            for img in session.execute(
                select(ReviewImage).where(
                    ReviewImage.review_id == review.id
                )
            ).scalars().all():
                if img.cloudinary_public_id:
                    cloudinary_public_ids.append(img.cloudinary_public_id)
                session.delete(img)
            session.delete(review)

        # Product images (DB rows now, Cloudinary after commit).
        for img in product.images:
            if isinstance(img, ProductImage) and img.cloudinary_public_id:
                cloudinary_public_ids.append(img.cloudinary_public_id)
            session.delete(img)

        for variant in product.variants:
            session.delete(variant)

        session.delete(product)
        deleted.append(str(product.id))
        rag_product_ids.append(str(product.id))

    session.commit() if commit else session.flush()
    return {
        "deleted": deleted,
        "blocked": blocked,
        "cloudinary_public_ids": cloudinary_public_ids,
        "rag_product_ids": rag_product_ids,
    }


def bulk_update_product_status(session: Session, product_ids: list[UUID], is_active: bool, *, commit: bool = True) -> int:
    """Bulk update product status"""
    if not product_ids:
        return 0
    
    statement = select(Product).where(Product.id.in_(product_ids))
    result = session.execute(statement)
    products = result.scalars().all()
    
    count = len(products)
    for product in products:
        product.is_active = is_active
    
    session.commit() if commit else session.flush()
    return count


def get_products_for_export(session: Session) -> list[dict]:
    """Get products in export format"""
    products = get_all_products(session)
    
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
                }
                for img in product.images
            ],
            "variants": [
                {
                    "id": str(v.id),
                    "sku": v.sku,
                    "attributes": v.attributes,
                    "price_override": str(v.price_override) if v.price_override else None,
                    "stock": v.stock,
                }
                for v in product.variants
            ],
        })
    
    return export_data


# =========================================================
# VARIANT HELPER FUNCTIONS
# =========================================================

def get_variant_by_product_and_sku(
    session: Session,
    product_id: UUID,
    sku: str,
) -> ProductVariant | None:
    """Get a variant by product ID and SKU"""
    statement = select(ProductVariant).where(
        ProductVariant.product_id == product_id,
        ProductVariant.sku == sku
    )
    result = session.execute(statement)
    return result.scalar_one_or_none()


def get_variants_by_product_ids(
    session: Session,
    product_ids: list[UUID],
) -> dict[UUID, list[ProductVariant]]:
    """Get variants for multiple products at once"""
    if not product_ids:
        return {}
    
    statement = select(ProductVariant).where(
        ProductVariant.product_id.in_(product_ids)
    )
    result = session.execute(statement)
    variants = result.scalars().all()
    
    # Group by product_id
    variants_by_product = {}
    for variant in variants:
        if variant.product_id not in variants_by_product:
            variants_by_product[variant.product_id] = []
        variants_by_product[variant.product_id].append(variant)
    
    return variants_by_product
