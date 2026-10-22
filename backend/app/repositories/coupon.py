from datetime import datetime, timezone
from random import choices
from string import ascii_uppercase, digits
from uuid import UUID

from sqlmodel import Session, select

from app.models.coupon import Coupon, CouponType
from app.models.order import Order, OrderStatus


def create_coupon(
    session: Session,
    coupon_data: dict,
    created_by: UUID,
    *, commit: bool = True,
) -> Coupon:
    """Create a new coupon"""
    coupon = Coupon(
        **coupon_data,
        created_by=created_by,
        times_used=0,
    )
    session.add(coupon)
    if commit:
        session.commit()
        session.refresh(coupon)
    else:
        session.flush()
    return coupon


def get_coupon_by_id(
    session: Session,
    coupon_id: UUID,
) -> Coupon | None:
    """Get coupon by ID"""
    return session.get(Coupon, coupon_id)


def get_coupon_by_code(
    session: Session,
    code: str,
) -> Coupon | None:
    """Get coupon by code"""
    statement = select(Coupon).where(Coupon.code == code)
    return session.exec(statement).first()


def get_all_coupons(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    is_active: bool | None = None,
    coupon_type: CouponType | None = None,
) -> list[Coupon]:
    """Get all coupons, optionally filtered by active state and type."""
    statement = select(Coupon).order_by(Coupon.created_at.desc())
    
    if is_active is not None:
        statement = statement.where(Coupon.is_active == is_active)
    if coupon_type is not None:
        statement = statement.where(Coupon.coupon_type == coupon_type)
    
    statement = statement.offset(skip).limit(limit)
    return session.exec(statement).all()


def update_coupon(
    session: Session,
    coupon: Coupon,
    coupon_data: dict,
    none_fields: list[str] | None = None,
    *, commit: bool = True,
) -> Coupon:
    """Update coupon.

    `none_fields` are explicitly set to None first (e.g. stale trigger
    payload cleared when the trigger type changes); the rest follow the
    existing behavior of skipping None values so partial updates don't
    wipe fields.
    """
    for key in none_fields or []:
        setattr(coupon, key, None)
    
    for key, value in coupon_data.items():
        if value is not None:
            setattr(coupon, key, value)
    
    coupon.updated_at = datetime.now(timezone.utc)
    session.add(coupon)
    if commit:
        session.commit()
        session.refresh(coupon)
    else:
        session.flush()
    return coupon


def delete_coupon(
    session: Session,
    coupon: Coupon,
    *, commit: bool = True,
) -> None:
    """Delete coupon"""
    session.delete(coupon)
    session.commit() if commit else session.flush()


def increment_coupon_usage(
    session: Session,
    coupon: Coupon,
    *,
    commit: bool = True,
) -> Coupon:
    """Increment usage, optionally within the caller's checkout transaction."""
    coupon.times_used += 1
    session.add(coupon)
    if commit:
        session.commit()
        session.refresh(coupon)
    else:
        session.flush()
    return coupon


def get_user_coupon_usage_count(
    session: Session,
    coupon_code: str,
    user_id: UUID,
) -> int:
    """
    Get how many times a user has successfully used a coupon.
    
    Only counts orders that are:
    - Not cancelled
    - Not refunded
    
    This ensures that if a user places an order and then cancels it,
    the cancelled order doesn't count toward their usage limit.
    """
    statement = select(Order).where(
        Order.coupon_code == coupon_code,
        Order.user_id == user_id,
        # ✅ Only count valid orders (not cancelled or refunded)
        Order.status.not_in([OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    )
    orders = session.exec(statement).all()
    return len(orders)


def get_completed_order_count(
    session: Session,
    user_id: UUID,
) -> int:
    """
    How many 'real' orders a user has placed (cancelled and refunded
    orders don't count). Used by the first_order trigger.
    """
    statement = select(Order).where(
        Order.user_id == user_id,
        Order.status.not_in([OrderStatus.CANCELLED, OrderStatus.REFUNDED]),
    )
    return len(session.exec(statement).all())


def get_active_automatic_coupons(session: Session) -> list[Coupon]:
    """All active AUTOMATIC coupons, newest first."""
    statement = (
        select(Coupon)
        .where(Coupon.coupon_type == CouponType.AUTOMATIC)
        .where(Coupon.is_active == True)  # noqa: E712
        .order_by(Coupon.created_at.desc())
    )
    return session.exec(statement).all()


def get_next_automatic_code(session: Session, length: int = 6) -> str:
    """Generate a unique AUTO- prefixed code for an automatic coupon."""
    for _ in range(50):
        code = "AUTO-" + "".join(choices(ascii_uppercase + digits, k=length))
        if not get_coupon_by_code(session, code):
            return code
    raise RuntimeError("Could not generate a unique automatic coupon code")
