from decimal import Decimal
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.api.deps import SessionDep, get_current_user
from app.models.cart import Cart, CartItem
from app.models.user import User
from app.repositories import cart as cart_repo
from app.repositories import coupon as coupon_repo
from app.schemas.cart import (
    AddToCartRequest,
    ApplyCouponRequest,
    CartRead,
    UpdateCartItemRequest,
)
from app.models.coupon import CouponType
from app.services.pricing import build_cart_read, resolve_cart_pricing
from app.utils.cart import calculate_cart_total
from app.core.region import format_money


router = APIRouter(prefix="/cart", tags=["Cart"])


def get_session_id(request: Request) -> str | None:
    """Get session ID from cookie or header"""
    session_id = request.cookies.get("cart_session_id")
    if session_id:
        return session_id
    return request.headers.get("X-Cart-Session-ID")


@router.get("", response_model=CartRead)
def get_cart(
    request: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Get current user's cart.
    
    - Authenticated users: Get their cart
    - Guest users: Get cart from session ID
    """
    session_id = get_session_id(request)
    user_id = current_user.id if current_user else None
    
    cart = cart_repo.get_or_create_cart(session, user_id, session_id)
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    # The pricing engine is the single source of truth: it re-validates the
    # manual coupon on the cart and decides whether an automatic coupon
    # applies itself (and for how much). The API just returns the decision.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)


@router.post("/items", response_model=CartRead, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    request: Request,
    item_data: AddToCartRequest,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Add item to cart.
    
    - If item already exists, quantity is increased
    - Validates stock availability
    """
    session_id = get_session_id(request)
    user_id = current_user.id if current_user else None
    
    cart = cart_repo.get_or_create_cart(session, user_id, session_id)
    
    try:
        if item_data.merge_key is not None:
            cart_repo.merge_cart_item(session, cart, item_data.variant_id,
                                      item_data.quantity, item_data.merge_key)
        else:
            cart_repo.add_item_to_cart(session, cart, item_data.variant_id, item_data.quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    # Pricing engine decides discounts (manual re-validation + automatic
    # coupon evaluation) — the API just returns what it decides.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)


@router.put("/items/{item_id}", response_model=CartRead)
def update_cart_item(
    item_id: UUID,
    item_data: UpdateCartItemRequest,
    request: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Update cart item quantity.
    """
    # Get cart item
    cart_item = session.get(CartItem, item_id)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Check ownership
    cart = session.get(Cart, cart_item.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    if current_user:
        if cart.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        session_id = get_session_id(request)
        if cart.session_id != session_id:
            raise HTTPException(status_code=403, detail="Not authorized")
    
    try:
        cart_repo.update_cart_item(session, cart_item, item_data.quantity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    # Pricing engine decides discounts (manual re-validation + automatic
    # coupon evaluation) — the API just returns what it decides.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)


@router.delete("/items/{item_id}", response_model=CartRead)
def remove_from_cart(
    item_id: UUID,
    request: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Remove item from cart.
    """
    # Get cart item
    cart_item = session.get(CartItem, item_id)
    if not cart_item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    # Check ownership
    cart = session.get(Cart, cart_item.cart_id)
    if not cart:
        raise HTTPException(status_code=404, detail="Cart not found")
    
    if current_user:
        if cart.user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    else:
        session_id = get_session_id(request)
        if cart.session_id != session_id:
            raise HTTPException(status_code=403, detail="Not authorized")
    
    cart_repo.remove_cart_item(session, cart_item)
    
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    # Pricing engine decides discounts (manual re-validation + automatic
    # coupon evaluation) — the API just returns what it decides.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)


@router.delete("", response_model=CartRead)
def clear_cart(
    request: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Clear all items from cart.
    """
    session_id = get_session_id(request)
    user_id = current_user.id if current_user else None
    
    cart = cart_repo.get_or_create_cart(session, user_id, session_id)
    cart_repo.clear_cart(session, cart)
    
    return CartRead(
        id=cart.id,
        items=[],
        subtotal=Decimal("0.00"),
        coupon_code=None,
        discount_total=Decimal("0.00"),
        tax_total=Decimal("0.00"),
        shipping_total=Decimal("0.00"),
        total=Decimal("0.00"),
        item_count=0
    )


@router.post("/coupon", response_model=CartRead)
def apply_coupon(
    request: ApplyCouponRequest,
    request_obj: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Apply coupon to cart.
    """
    session_id = get_session_id(request_obj)
    user_id = current_user.id if current_user else None
    
    cart = cart_repo.get_or_create_cart(session, user_id, session_id)
    
    # ✅ VALIDATE COUPON BEFORE APPLYING
    coupon = coupon_repo.get_coupon_by_code(session, request.coupon_code)
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coupon not found"
        )
    
    # Automatic coupons apply themselves — they cannot be typed in as codes
    if coupon.coupon_type == CouponType.AUTOMATIC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon is applied automatically and cannot be entered as a code",
        )
    
    # Check if coupon is active
    if not coupon.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon is currently inactive"
        )
    
    # Check if coupon is valid from date
    if coupon.valid_from and coupon.valid_from > datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This coupon will be available from {coupon.valid_from.strftime('%d %b %Y')}"
        )
    
    # Check if coupon is expired
    if coupon.valid_until and coupon.valid_until < datetime.now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This coupon expired on {coupon.valid_until.strftime('%d %b %Y')}"
        )
    
    # Check global usage limit
    if coupon.max_uses and coupon.times_used >= coupon.max_uses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sorry, this coupon has reached its maximum usage limit ({coupon.max_uses} uses)"
        )
    
    # ✅ Check user's per-user limit (THIS IS THE KEY FIX!)
    if user_id and coupon.max_uses_per_user:
        user_usage = coupon_repo.get_user_coupon_usage_count(
            session, request.coupon_code, user_id
        )
        if user_usage >= coupon.max_uses_per_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You have already used this coupon. Maximum {coupon.max_uses_per_user} use(s) per customer."
            )
    
    # Check min order value
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    totals = calculate_cart_total(cart_with_items)
    subtotal = totals["subtotal"]
    
    if coupon.min_order_value and subtotal < coupon.min_order_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum order value of {format_money(coupon.min_order_value)} required. Current subtotal: {format_money(subtotal)}"
        )
    # ✅ END OF VALIDATION BLOCK
    
    # If same coupon already applied, just return the cart with its discount
    if cart.coupon_code == request.coupon_code:
        cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
        pricing = resolve_cart_pricing(session, cart_with_items, current_user)
        return build_cart_read(cart_with_items, pricing)
    
    try:
        cart_repo.apply_coupon_to_cart(session, cart, request.coupon_code)
    except ValueError as e:
        # Return user-friendly error message
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)


@router.delete("/coupon", response_model=CartRead)
def remove_coupon(
    request_obj: Request,
    session: SessionDep,
    current_user: User | None = Depends(get_current_user),
):
    """
    Remove coupon from cart.
    """
    session_id = get_session_id(request_obj)
    user_id = current_user.id if current_user else None
    
    cart = cart_repo.get_or_create_cart(session, user_id, session_id)
    cart = cart_repo.remove_coupon_from_cart(session, cart)
    
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    # Pricing engine decides discounts (manual re-validation + automatic
    # coupon evaluation) — the API just returns what it decides.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    return build_cart_read(cart_with_items, pricing)
