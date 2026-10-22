# app/api/v1/admin/reviews.py
"""Admin review moderation (requires reviews.moderate — admins only).

Storefront review paths show visible reviews exclusively; hidden reviews
stay in the DB as the audit trail. Every hide/unhide/delete writes an
audit entry (entity "review" — operational, visible to reports.view).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import review as review_repo
from app.schemas.review import (
    AdminReviewRead,
    ReviewListResponse,
    ReviewVisibilityUpdate,
)
from app.services.cloudinary_service import delete_image

router = APIRouter(prefix="/admin/reviews", tags=["Admin Reviews"])


@router.get("", response_model=ReviewListResponse)
def list_reviews(
    session: SessionDep,
    current_user: User = Depends(require_perm("reviews.moderate")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    rating: int | None = Query(default=None, ge=1, le=5),
    product_id: UUID | None = Query(default=None),
    hidden: bool | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
):
    """Paginated moderation queue, newest first (hidden included)."""
    skip = (page - 1) * limit
    rows, total = review_repo.list_reviews_admin(
        session,
        skip=skip,
        limit=limit,
        rating=rating,
        product_id=product_id,
        hidden=hidden,
        search=search,
    )
    return ReviewListResponse(
        items=[AdminReviewRead(**row) for row in rows],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if limit else 1,
    )


@router.put("/{review_id}/visibility", response_model=AdminReviewRead)
def set_review_visibility(
    review_id: UUID,
    payload: ReviewVisibilityUpdate,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("reviews.moderate")),
):
    """Hide (abuse/spam) or unhide a review. Storefront updates instantly."""
    review = review_repo.get_review_by_id(session, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )
    was_hidden = bool(review.is_hidden)
    review.is_hidden = bool(payload.is_hidden)
    session.add(review)
    audit_repo.log_and_commit(
        session,
        action="review.hidden" if review.is_hidden else "review.visible",
        entity="review",
        entity_id=review.id,
        actor_id=current_user.id,
        before={"is_hidden": was_hidden},
        after={"is_hidden": review.is_hidden},
        ip_address=audit_repo.client_ip(request),
    )
    fresh = session.get(review_repo.Review, review.id)
    from app.models.product import Product

    product = session.get(Product, fresh.product_id)
    from app.models.user import User as UserModel

    author = session.get(UserModel, fresh.user_id)
    return AdminReviewRead(
        id=fresh.id,
        product_id=fresh.product_id,
        product_name=product.name if product else None,
        user_id=fresh.user_id,
        user_full_name=author.full_name if author else None,
        user_email=author.email if author else None,
        order_id=fresh.order_id,
        rating=fresh.rating,
        title=fresh.title,
        comment=fresh.comment,
        is_verified_purchase=fresh.is_verified_purchase,
        is_hidden=fresh.is_hidden,
        created_at=fresh.created_at,
        updated_at=fresh.updated_at,
        images=review_repo.get_review_images(session, fresh.id),
    )


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: UUID,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("reviews.moderate")),
):
    """Hard-delete a review (spam/abuse with no record value). Audited."""
    review = review_repo.get_review_by_id(session, review_id)
    if review is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Review not found"
        )
    snapshot = {
        "product_id": str(review.product_id),
        "user_id": str(review.user_id),
        "rating": review.rating,
        "title": review.title,
    }
    images = review_repo.get_review_images(session, review.id)
    public_ids = [image.cloudinary_public_id for image in images]
    for image in images:
        session.delete(image)
    session.flush()
    review_repo.delete_review(session, review, commit=False)
    audit_repo.log_and_commit(
        session,
        action="review.deleted",
        entity="review",
        entity_id=review_id,
        actor_id=current_user.id,
        before=snapshot,
        ip_address=audit_repo.client_ip(request),
    )
    for public_id in public_ids:
        delete_image(public_id)
    return None
