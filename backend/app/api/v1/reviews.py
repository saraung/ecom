from uuid import UUID

import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.api.deps import SessionDep, CurrentUser
from app.models.user import User
from app.models.review_image import ReviewImage
from app.repositories import review as review_repo
from app.repositories import product as product_repo
from app.repositories import order as order_repo
from app.schemas.review import ReviewCreate, ReviewRead, ReviewUpdate
from app.services.cloudinary_service import delete_image, upload_image


router = APIRouter(prefix="/reviews", tags=["Reviews"])


def _review_read(session, review, user):
    return ReviewRead(
        id=review.id, product_id=review.product_id, user_id=review.user_id,
        order_id=review.order_id, rating=review.rating, title=review.title,
        comment=review.comment, is_verified_purchase=review.is_verified_purchase,
        is_hidden=review.is_hidden, created_at=review.created_at,
        updated_at=review.updated_at, user_full_name=user.full_name,
        images=review_repo.get_review_images(session, review.id),
    )


@router.post("/{product_id}", response_model=ReviewRead)
def create_review(
    product_id: UUID,
    review_data: ReviewCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Create a review for a product — requires a verified purchase"""
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if review_repo.has_reviewed_product(session, current_user.id, product_id):
        raise HTTPException(
            status_code=400,
            detail="You have already reviewed this product"
        )

    order_id = order_repo.get_verified_purchase_order_id(
        session, current_user.id, product_id
    )
    if not order_id:
        raise HTTPException(
            status_code=403,
            detail="You can only review products you have purchased and received"
        )

    review = review_repo.create_review(
        session,
        product_id,
        current_user.id,
        review_data.model_dump(),
        order_id=order_id,
        is_verified_purchase=True,
    )

    return _review_read(session, review, current_user)


@router.post("/{product_id}/with-images", response_model=ReviewRead)
async def create_review_with_images(
    product_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    """Create a verified review and upload up to six Cloudinary photos."""
    try:
        review_data = ReviewCreate.model_validate_json(data)
    except Exception as exc:
        raise HTTPException(422, "Invalid review data") from exc
    if len(files) > 6:
        raise HTTPException(422, "At most 6 review images are allowed")
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if review_repo.has_reviewed_product(session, current_user.id, product_id):
        raise HTTPException(400, "You have already reviewed this product")
    order_id = order_repo.get_verified_purchase_order_id(session, current_user.id, product_id)
    if not order_id:
        raise HTTPException(403, "You can only review products you have purchased and received")
    blobs = []
    for file in files:
        if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(415, "Review images must be JPEG, PNG or WebP")
        blob = await file.read(5 * 1024 * 1024 + 1)
        if len(blob) > 5 * 1024 * 1024:
            raise HTTPException(413, "Review images must be 5 MB or smaller")
        try:
            with Image.open(io.BytesIO(blob)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise HTTPException(415, "One review file is not a readable image") from exc
        blobs.append((file.filename or "review-image", blob))
    uploaded = []
    try:
        review = review_repo.create_review(
            session, product_id, current_user.id, review_data.model_dump(),
            order_id=order_id, is_verified_purchase=True, commit=False,
        )
        for index, (filename, blob) in enumerate(blobs):
            asset = upload_image(blob, folder=f"com/reviews/{review.id}", filename=filename)
            uploaded.append(asset)
            session.add(ReviewImage(review_id=review.id, secure_url=asset["secure_url"], cloudinary_public_id=asset["public_id"], filename=filename[:160], sort_order=index))
        session.flush()
        result = _review_read(session, review, current_user)
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        for asset in uploaded:
            delete_image(asset.get("public_id"))
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, "Review image upload failed") from exc


@router.get("/products/{product_id}", response_model=list[ReviewRead])
def get_product_reviews(
    product_id: UUID,
    session: SessionDep,
    skip: int = 0,
    limit: int = 20,
):
    """Get all reviews for a product"""
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return review_repo.get_reviews_by_product(session, product_id, skip, limit)


@router.get("/product/{product_id}/rating", response_model=dict)
def get_product_rating(
    product_id: UUID,
    session: SessionDep,
):
    """Get average rating for a product"""
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    avg_rating = review_repo.get_product_average_rating(session, product_id)
    return {"average_rating": avg_rating}


@router.get("/my-reviews", response_model=list[ReviewRead])
def get_my_reviews(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
):
    """Get all reviews by current user"""
    return review_repo.get_reviews_by_user(session, current_user.id, skip, limit)


@router.put("/{review_id}", response_model=ReviewRead)
def update_review(
    review_id: UUID,
    review_data: ReviewUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Update a review"""
    review = review_repo.get_review_by_id(session, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    review = review_repo.update_review(
        session,
        review,
        review_data.model_dump(exclude_unset=True)
    )

    return _review_read(session, review, current_user)


@router.delete("/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(
    review_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Delete a review"""
    review = review_repo.get_review_by_id(session, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    images = review_repo.get_review_images(session, review.id)
    public_ids = [image.cloudinary_public_id for image in images]
    for image in images:
        session.delete(image)
    session.flush()
    review_repo.delete_review(session, review)
    for public_id in public_ids:
        delete_image(public_id)
    return None
