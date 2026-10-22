from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import product as product_repo
from app.repositories import audit as audit_repo
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductPage,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantRead,
    ProductVariantUpdate,
)
from app.utils.pricing import (
    get_product_pricing_data,
    get_variant_pricing_data,
)
from app.services.rag_service import ingest_all_products, delete_product_from_rag  # ✅ Import RAG functions


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.get(
    "/",
    response_model=list[ProductRead] | ProductPage,
)
def get_products(
    session: SessionDep,

    search: str | None = Query(
        default=None,
        min_length=1,
        max_length=100,
    ),

    # Category filter
    category_id: UUID | None = None,

    # Price filters
    min_price: Decimal | None = Query(
        default=None,
        ge=0,
    ),

    max_price: Decimal | None = Query(
        default=None,
        ge=0,
    ),

    # Sorting
    sort: str = Query(
        default="newest",
        pattern="^(newest|oldest|price_asc|price_desc|name_asc|name_desc)$",
    ),

    # Pagination
    page: int = Query(
        default=1,
        ge=1,
    ),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    include_pagination: bool = False,
    include_descendants: bool = False,
):
    """
    Get active products.
    """

    # Make sure the price range is valid.
    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_price cannot be greater than max_price",
        )

    # Convert page number into database offset.
    skip = (page - 1) * limit

    products = product_repo.get_products(
        session=session,
        search=search,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        skip=skip,
        limit=limit,
        include_descendants=include_descendants,
    )

    # Batch-fetch rating stats for all products in this page in ONE query
    product_ids = [product.id for product in products]
    rating_stats = product_repo.get_product_rating_stats(session, product_ids)

    # Create response objects with computed fields
    response_products = []
    for product in products:
        pricing_data = get_product_pricing_data(product)
        stats = rating_stats.get(
            product.id,
            {"average_rating": 0.0, "review_count": 0},
        )

        # Create ProductRead instance with all data
        product_read = ProductRead(
            id=product.id,
            name=product.name,
            slug=product.slug,
            description=product.description,
            category_id=product.category_id,
            price=product.price,
            compare_at_price=product.compare_at_price,
            is_active=product.is_active,
            created_by=product.created_by,
            created_at=product.created_at,
            updated_at=product.updated_at,
            variants=[],  # Will fill below
            images=product.images,  # Images are already loaded
            discount_percentage=pricing_data["discount_percentage"],
            savings_amount=pricing_data["savings_amount"],
            is_on_sale=pricing_data["is_on_sale"],
            average_rating=stats["average_rating"],
            review_count=stats["review_count"],
        )
        
        # Add variants with computed fields
        for variant in product.variants:
            variant_pricing = get_variant_pricing_data(product, variant)
            
            variant_read = ProductVariantRead(
                id=variant.id,
                product_id=variant.product_id,
                sku=variant.sku,
                attributes=variant.attributes,
                price_override=variant.price_override,
                stock=variant.stock,
                created_at=variant.created_at,
                effective_price=variant_pricing["effective_price"],
                discount_percentage=variant_pricing["discount_percentage"],
                savings_amount=variant_pricing["savings_amount"],
                is_on_sale=variant_pricing["is_on_sale"],
            )
            product_read.variants.append(variant_read)
        
        response_products.append(product_read)

    if include_pagination:
        total = product_repo.count_catalog_products(session, search=search, category_id=category_id,
                                                    min_price=min_price, max_price=max_price,
                                                    include_descendants=include_descendants)
        return ProductPage(products=response_products, total=total, page=page, limit=limit,
                           total_pages=(total + limit - 1) // limit)
    return response_products


@router.get(
    "/{slug}",
    response_model=ProductRead,
)
def get_product(
    slug: str,
    session: SessionDep,
):
    """
    Get a single product by slug.
    """

    product = product_repo.get_product_by_slug(
        session,
        slug,
    )

    if not product or not product.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Create response object with computed fields
    pricing_data = get_product_pricing_data(product)

    # Fetch rating stats for this single product
    rating_stats = product_repo.get_product_rating_stats(session, [product.id])
    stats = rating_stats.get(
        product.id,
        {"average_rating": 0.0, "review_count": 0},
    )
    
    product_read = ProductRead(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        category_id=product.category_id,
        price=product.price,
        compare_at_price=product.compare_at_price,
        is_active=product.is_active,
        created_by=product.created_by,
        created_at=product.created_at,
        updated_at=product.updated_at,
        variants=[],  # Will fill below
        images=product.images,
        discount_percentage=pricing_data["discount_percentage"],
        savings_amount=pricing_data["savings_amount"],
        is_on_sale=pricing_data["is_on_sale"],
        average_rating=stats["average_rating"],
        review_count=stats["review_count"],
    )
    
    # Add variants with computed fields
    for variant in product.variants:
        variant_pricing = get_variant_pricing_data(product, variant)
        
        variant_read = ProductVariantRead(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            attributes=variant.attributes,
            price_override=variant.price_override,
            stock=variant.stock,
            created_at=variant.created_at,
            effective_price=variant_pricing["effective_price"],
            discount_percentage=variant_pricing["discount_percentage"],
            savings_amount=variant_pricing["savings_amount"],
            is_on_sale=variant_pricing["is_on_sale"],
        )
        product_read.variants.append(variant_read)

    return product_read


# =========================================================
# PRODUCTS - STAFF+
# =========================================================

@router.post(
    "/",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product(
    product_data: ProductCreate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(
        require_perm("products.create")
    ),
):
    """
    Create a product.
    """

    existing = product_repo.get_product_by_slug(
        session,
        product_data.slug,
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with this slug already exists",
        )

    product = product_repo.create_product(
        session,
        product_data,
        current_user.id,
        commit=False,
    )
    audit_repo.log_and_commit(
        session, action="product.created", entity="product",
        entity_id=product.id, actor_id=current_user.id,
        after={"name": product.name, "slug": product.slug,
               "price": str(product.price)},
        ip_address=audit_repo.client_ip(request),
    )

    # ✅ Sync product to RAG after creation
    try:
        count = ingest_all_products(session)
        print(f"✅ Synced {count} products to RAG after product creation")
    except Exception as e:
        print(f"⚠️ Failed to sync products to RAG: {e}")

    # Create response object with computed fields
    pricing_data = get_product_pricing_data(product)
    
    product_read = ProductRead(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        category_id=product.category_id,
        price=product.price,
        compare_at_price=product.compare_at_price,
        is_active=product.is_active,
        created_by=product.created_by,
        created_at=product.created_at,
        updated_at=product.updated_at,
        variants=[],
        images=product.images,
        discount_percentage=pricing_data["discount_percentage"],
        savings_amount=pricing_data["savings_amount"],
        is_on_sale=pricing_data["is_on_sale"],
        average_rating=0.0,
        review_count=0,
    )
    
    # Add variants with computed fields
    for variant in product.variants:
        variant_pricing = get_variant_pricing_data(product, variant)
        
        variant_read = ProductVariantRead(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            attributes=variant.attributes,
            price_override=variant.price_override,
            stock=variant.stock,
            created_at=variant.created_at,
            effective_price=variant_pricing["effective_price"],
            discount_percentage=variant_pricing["discount_percentage"],
            savings_amount=variant_pricing["savings_amount"],
            is_on_sale=variant_pricing["is_on_sale"],
        )
        product_read.variants.append(variant_read)

    return product_read


@router.put(
    "/{product_id}",
    response_model=ProductRead,
)
def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(
        require_perm("products.update")
    ),
):
    """
    Update a product.
    """

    product = product_repo.get_product_by_id(
        session,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # If slug is being changed, check uniqueness
    if (
        product_data.slug is not None
        and product_data.slug != product.slug
    ):
        existing = product_repo.get_product_by_slug(
            session,
            product_data.slug,
        )

        if existing and existing.id != product.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product with this slug already exists",
            )

    before = {"name": product.name, "slug": product.slug,
              "price": str(product.price),
              "compare_at_price": str(product.compare_at_price),
              "is_active": product.is_active}
    product = product_repo.update_product(
        session,
        product,
        product_data,
        commit=False,
    )
    audit_repo.log_and_commit(
        session, action="product.updated", entity="product",
        entity_id=product.id, actor_id=current_user.id,
        before=before,
        after={"name": product.name, "slug": product.slug,
               "price": str(product.price),
               "compare_at_price": str(product.compare_at_price),
               "is_active": product.is_active},
        ip_address=audit_repo.client_ip(request),
    )

    # ✅ Sync product to RAG after update
    try:
        count = ingest_all_products(session)
        print(f"✅ Synced {count} products to RAG after product update")
    except Exception as e:
        print(f"⚠️ Failed to sync products to RAG: {e}")

    # Create response object with computed fields
    pricing_data = get_product_pricing_data(product)

    # Fetch this product's real rating stats (it may already have reviews)
    rating_stats = product_repo.get_product_rating_stats(session, [product.id])
    stats = rating_stats.get(
        product.id,
        {"average_rating": 0.0, "review_count": 0},
    )
    
    product_read = ProductRead(
        id=product.id,
        name=product.name,
        slug=product.slug,
        description=product.description,
        category_id=product.category_id,
        price=product.price,
        compare_at_price=product.compare_at_price,
        is_active=product.is_active,
        created_by=product.created_by,
        created_at=product.created_at,
        updated_at=product.updated_at,
        variants=[],
        images=product.images,
        discount_percentage=pricing_data["discount_percentage"],
        savings_amount=pricing_data["savings_amount"],
        is_on_sale=pricing_data["is_on_sale"],
        average_rating=stats["average_rating"],
        review_count=stats["review_count"],
    )
    
    # Add variants with computed fields
    for variant in product.variants:
        variant_pricing = get_variant_pricing_data(product, variant)
        
        variant_read = ProductVariantRead(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            attributes=variant.attributes,
            price_override=variant.price_override,
            stock=variant.stock,
            created_at=variant.created_at,
            effective_price=variant_pricing["effective_price"],
            discount_percentage=variant_pricing["discount_percentage"],
            savings_amount=variant_pricing["savings_amount"],
            is_on_sale=variant_pricing["is_on_sale"],
        )
        product_read.variants.append(variant_read)

    return product_read


# =========================================================
# PRODUCTS - ADMIN ONLY
# =========================================================

@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product(
    product_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(
        require_perm("products.delete")
    ),
):
    """
    Deactivate a product.
    """

    product = product_repo.get_product_by_id(
        session,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    snapshot = {"name": product.name, "slug": product.slug,
                "price": str(product.price)}
    product_repo.delete_product(
        session,
        product,
        commit=False,
    )
    audit_repo.log_and_commit(
        session, action="product.deleted", entity="product",
        entity_id=product_id, actor_id=current_user.id,
        before=snapshot,
        ip_address=audit_repo.client_ip(request),
    )

    # ✅ Remove product from RAG after deletion
    try:
        delete_product_from_rag(product_id)
        print(f"✅ Removed product {product_id} from RAG")
    except Exception as e:
        print(f"⚠️ Failed to remove product from RAG: {e}")

    return None


# =========================================================
# PRODUCT VARIANTS - PUBLIC
# =========================================================

@router.get(
    "/{product_id}/variants",
    response_model=list[ProductVariantRead],
)
def get_product_variants(
    product_id: UUID,
    session: SessionDep,
):
    """
    Get all variants for a product.
    """

    product = product_repo.get_product_by_id(
        session,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    variants = product_repo.get_variants(
        session,
        product_id,
    )

    # Create response objects with computed fields
    response_variants = []
    for variant in variants:
        variant_pricing = get_variant_pricing_data(product, variant)
        
        variant_read = ProductVariantRead(
            id=variant.id,
            product_id=variant.product_id,
            sku=variant.sku,
            attributes=variant.attributes,
            price_override=variant.price_override,
            stock=variant.stock,
            created_at=variant.created_at,
            effective_price=variant_pricing["effective_price"],
            discount_percentage=variant_pricing["discount_percentage"],
            savings_amount=variant_pricing["savings_amount"],
            is_on_sale=variant_pricing["is_on_sale"],
        )
        response_variants.append(variant_read)

    return response_variants


# =========================================================
# PRODUCT VARIANTS - STAFF+
# =========================================================

@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantRead,
    status_code=status.HTTP_201_CREATED,
)
def create_product_variant(
    product_id: UUID,
    variant_data: ProductVariantCreate,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("products.create")
    ),
):
    """
    Create a product variant.
    """

    product = product_repo.get_product_by_id(
        session,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    existing = product_repo.get_variant_by_sku(
        session,
        variant_data.sku,
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variant with this SKU already exists",
        )

    variant = product_repo.create_variant(
        session,
        product_id,
        variant_data,
    )

    # ✅ Sync product to RAG after variant creation
    try:
        count = ingest_all_products(session)
        print(f"✅ Synced {count} products to RAG after variant creation")
    except Exception as e:
        print(f"⚠️ Failed to sync products to RAG: {e}")

    # Create response object with computed fields
    variant_pricing = get_variant_pricing_data(product, variant)
    
    variant_read = ProductVariantRead(
        id=variant.id,
        product_id=variant.product_id,
        sku=variant.sku,
        attributes=variant.attributes,
        price_override=variant.price_override,
        stock=variant.stock,
        created_at=variant.created_at,
        effective_price=variant_pricing["effective_price"],
        discount_percentage=variant_pricing["discount_percentage"],
        savings_amount=variant_pricing["savings_amount"],
        is_on_sale=variant_pricing["is_on_sale"],
    )

    return variant_read


@router.put(
    "/{product_id}/variants/{variant_id}",
    response_model=ProductVariantRead,
)
def update_product_variant(
    product_id: UUID,
    variant_id: UUID,
    variant_data: ProductVariantUpdate,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("products.update")
    ),
):
    """
    Update a product variant.
    """

    product = product_repo.get_product_by_id(
        session,
        product_id,
    )

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    variant = product_repo.get_variant_by_id(
        session,
        variant_id,
    )

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found",
        )

    # Make sure the variant belongs to this product.
    if variant.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant does not belong to this product",
        )

    # If SKU is being changed, check uniqueness
    if (
        variant_data.sku is not None
        and variant_data.sku != variant.sku
    ):
        existing = product_repo.get_variant_by_sku(
            session,
            variant_data.sku,
        )

        if existing and existing.id != variant.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Variant with this SKU already exists",
            )

    variant = product_repo.update_variant(
        session,
        variant,
        variant_data,
    )

    # ✅ Sync product to RAG after variant update
    try:
        count = ingest_all_products(session)
        print(f"✅ Synced {count} products to RAG after variant update")
    except Exception as e:
        print(f"⚠️ Failed to sync products to RAG: {e}")

    # Create response object with computed fields
    variant_pricing = get_variant_pricing_data(product, variant)
    
    variant_read = ProductVariantRead(
        id=variant.id,
        product_id=variant.product_id,
        sku=variant.sku,
        attributes=variant.attributes,
        price_override=variant.price_override,
        stock=variant.stock,
        created_at=variant.created_at,
        effective_price=variant_pricing["effective_price"],
        discount_percentage=variant_pricing["discount_percentage"],
        savings_amount=variant_pricing["savings_amount"],
        is_on_sale=variant_pricing["is_on_sale"],
    )

    return variant_read


# =========================================================
# PRODUCT VARIANTS - STAFF+ (DELETE)
# =========================================================

@router.delete(
    "/{product_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_product_variant(
    product_id: UUID,
    variant_id: UUID,
    session: SessionDep,
    current_user: User = Depends(
        # Variant deletion keeps the legacy staff+ access: it is part of
        # day-to-day catalog work, covered by products.update.
        require_perm("products.update")
    ),
):
    """
    Delete a product variant.
    """
    
    # Check if product exists
    product = product_repo.get_product_by_id(
        session,
        product_id,
    )
    
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    
    # Check if variant exists
    variant = product_repo.get_variant_by_id(
        session,
        variant_id,
    )
    
    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found",
        )
    
    # Make sure the variant belongs to this product
    if variant.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant does not belong to this product",
        )
    
    # Delete the variant
    product_repo.delete_variant(
        session,
        variant,
    )

    # ✅ Sync product to RAG after variant deletion
    try:
        count = ingest_all_products(session)
        print(f"✅ Synced {count} products to RAG after variant deletion")
    except Exception as e:
        print(f"⚠️ Failed to sync products to RAG: {e}")
    
    return None
