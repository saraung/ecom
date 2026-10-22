from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import SessionDep, CurrentUser
from app.models.user import User
from app.repositories import wishlist as wishlist_repo
from app.repositories import product as product_repo
from app.schemas.wishlist import WishlistItemRead, WishlistResponse


router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


@router.get("", response_model=WishlistResponse)
def get_wishlist(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
):
    """Get user's wishlist"""
    items = wishlist_repo.get_user_wishlist(session, current_user.id, skip, limit)
    
    # Enrich with product details
    enriched_items = []
    for item in items:
        product = item.product
        enriched_items.append(
            WishlistItemRead(
                id=item.id,
                user_id=item.user_id,
                product_id=item.product_id,
                created_at=item.created_at,
                product_name=product.name if product else None,
                product_slug=product.slug if product else None,
                product_price=str(product.price) if product else None,
                product_image=product.images[0].url if product and product.images else None,
            )
        )
    
    return WishlistResponse(
        items=enriched_items,
        total=len(enriched_items)
    )


@router.post("/{product_id}", response_model=WishlistItemRead, status_code=status.HTTP_201_CREATED)
def add_to_wishlist(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Add product to wishlist"""
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    item = wishlist_repo.add_to_wishlist(session, current_user.id, product_id)
    
    return WishlistItemRead(
        id=item.id,
        user_id=item.user_id,
        product_id=item.product_id,
        created_at=item.created_at,
        product_name=product.name,
        product_slug=product.slug,
        product_price=str(product.price),
        product_image=product.images[0].url if product.images else None,
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_wishlist(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Remove product from wishlist"""
    removed = wishlist_repo.remove_from_wishlist(session, current_user.id, product_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found in wishlist")
    
    return None


@router.get("/check/{product_id}", response_model=dict)
def check_wishlist(
    product_id: UUID,
    session: SessionDep,
    current_user:CurrentUser,
):
    """Check if product is in wishlist"""
    in_wishlist = wishlist_repo.is_in_wishlist(session, current_user.id, product_id)
    return {"in_wishlist": in_wishlist}