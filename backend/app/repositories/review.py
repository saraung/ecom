from uuid import UUID

from sqlalchemy import select, func
from sqlmodel import Session

from app.models.review import Review
from app.models.review_image import ReviewImage
from app.models.user import User
from app.schemas.review import ReviewRead


def create_review(
    session: Session,
    product_id: UUID,
    user_id: UUID,
    review_data: dict,
    order_id: UUID | None = None,
    is_verified_purchase: bool = False,
    *, commit: bool = True,
) -> Review:
    """Create a new review"""
    review = Review(
        product_id=product_id,
        user_id=user_id,
        order_id=order_id,
        is_verified_purchase=is_verified_purchase,
        **review_data
    )
    session.add(review)
    if commit:
        session.commit()
        session.refresh(review)
    else:
        session.flush()
    return review


def get_review_images(session: Session, review_id: UUID) -> list[ReviewImage]:
    return session.execute(select(ReviewImage).where(ReviewImage.review_id == review_id)
                           .order_by(ReviewImage.sort_order, ReviewImage.id)).scalars().all()


def _to_review_read(session: Session, review: Review, full_name: str | None) -> ReviewRead:
    """Shared builder so the field list only lives in one place"""
    return ReviewRead(
        id=review.id,
        product_id=review.product_id,
        user_id=review.user_id,
        order_id=review.order_id,
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified_purchase=review.is_verified_purchase,
        is_hidden=review.is_hidden,
        created_at=review.created_at,
        updated_at=review.updated_at,
        user_full_name=full_name,
        images=get_review_images(session, review.id),
    )


def get_reviews_by_product(
    session: Session,
    product_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> list[ReviewRead]:
    """Get all VISIBLE reviews for a product with user info.

    Hidden (moderated) reviews are excluded from every storefront path —
    admins see them via :func:`list_reviews_admin` instead.
    """
    statement = (
        select(Review, User.full_name)
        .join(User, Review.user_id == User.id)
        .where(Review.product_id == product_id, Review.is_hidden == False)  # noqa: E712
        .order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = session.execute(statement)
    return [_to_review_read(session, review, full_name) for review, full_name in result]


def get_review_by_id(session: Session, review_id: UUID) -> Review | None:
    """Get a review by ID"""
    return session.get(Review, review_id)


def get_reviews_by_user(
    session: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> list[ReviewRead]:
    """Get all reviews by a user with user info"""
    statement = (
        select(Review, User.full_name)
        .join(User, Review.user_id == User.id)
        .where(Review.user_id == user_id)
        .order_by(Review.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = session.execute(statement)
    return [_to_review_read(session, review, full_name) for review, full_name in result]


def has_reviewed_product(session: Session, user_id: UUID, product_id: UUID) -> bool:
    """Efficient existence check for the duplicate-review guard"""
    statement = select(Review.id).where(
        Review.user_id == user_id,
        Review.product_id == product_id,
    )
    return session.execute(statement).first() is not None


def get_product_average_rating(
    session: Session,
    product_id: UUID,
) -> float:
    """Get average rating for a product (visible reviews only)."""
    statement = select(func.avg(Review.rating)).where(
        Review.product_id == product_id, Review.is_hidden == False  # noqa: E712
    )
    result = session.execute(statement)
    return round(result.scalar() or 0, 1)


def update_review(
    session: Session,
    review: Review,
    review_data: dict,
) -> Review:
    """Update a review"""
    for key, value in review_data.items():
        if value is not None:
            setattr(review, key, value)

    session.add(review)
    session.commit()
    session.refresh(review)
    return review


def delete_review(session: Session, review: Review, *, commit: bool = True) -> None:
    """Delete a review"""
    session.delete(review)
    session.commit() if commit else session.flush()


def list_reviews_admin(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    rating: int | None = None,
    product_id: UUID | None = None,
    hidden: bool | None = None,
    search: str | None = None,
) -> tuple[list[dict], int]:
    """Paginated review list for moderation (hidden included).

    Returns (rows, total) where each row carries product_name + reviewer
    identity for the admin table. Newest first.
    """
    from app.models.product import Product

    filters = []
    if rating is not None:
        filters.append(Review.rating == rating)
    if product_id is not None:
        filters.append(Review.product_id == product_id)
    if hidden is not None:
        filters.append(Review.is_hidden == hidden)
    if search:
        like = f"%{search.strip()}%"
        filters.append(
            (Review.title.ilike(like))
            | (Review.comment.ilike(like))
            | (User.email.ilike(like))
        )

    base = (
        select(Review, User.full_name, User.email, Product.name)
        .join(User, Review.user_id == User.id)
        .join(Product, Review.product_id == Product.id)
        .where(*filters)
        .order_by(Review.created_at.desc())
    )
    total = session.execute(
        select(func.count())
        .select_from(Review)
        .join(User, Review.user_id == User.id)
        .where(*filters)
    ).scalar_one()
    rows = session.exec(base.offset(skip).limit(limit)).all()
    return (
        [
            {
                "id": r.id,
                "product_id": r.product_id,
                "product_name": pname,
                "user_id": r.user_id,
                "user_full_name": fname,
                "user_email": email,
                "order_id": r.order_id,
                "rating": r.rating,
                "title": r.title,
                "comment": r.comment,
                "is_verified_purchase": r.is_verified_purchase,
                "is_hidden": r.is_hidden,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
                "images": get_review_images(session, r.id),
            }
            for r, fname, email, pname in rows
        ],
        int(total or 0),
    )
