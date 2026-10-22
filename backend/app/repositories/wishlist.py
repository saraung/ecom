from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.wishlist import Wishlist
from app.models.product import Product


def add_to_wishlist(
    session: Session,
    user_id: UUID,
    product_id: UUID,
) -> Wishlist:
    """Add product to wishlist"""
    # Check if already exists
    statement = select(Wishlist).where(
        Wishlist.user_id == user_id,
        Wishlist.product_id == product_id
    )
    existing = session.exec(statement).first()
    if existing:
        return existing
    
    wishlist_item = Wishlist(
        user_id=user_id,
        product_id=product_id
    )
    session.add(wishlist_item)
    session.commit()
    session.refresh(wishlist_item)
    return wishlist_item


def remove_from_wishlist(
    session: Session,
    user_id: UUID,
    product_id: UUID,
) -> bool:
    """Remove product from wishlist"""
    statement = select(Wishlist).where(
        Wishlist.user_id == user_id,
        Wishlist.product_id == product_id
    )
    wishlist_item = session.exec(statement).first()
    if wishlist_item:
        session.delete(wishlist_item)
        session.commit()
        return True
    return False


def get_user_wishlist(
    session: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
) -> list[Wishlist]:
    """Get all wishlist items for a user"""
    statement = (
        select(Wishlist)
        .where(Wishlist.user_id == user_id)
        .options(selectinload(Wishlist.product))
        .order_by(Wishlist.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()


def is_in_wishlist(
    session: Session,
    user_id: UUID,
    product_id: UUID,
) -> bool:
    """Check if product is in user's wishlist"""
    statement = select(Wishlist).where(
        Wishlist.user_id == user_id,
        Wishlist.product_id == product_id
    )
    return session.exec(statement).first() is not None