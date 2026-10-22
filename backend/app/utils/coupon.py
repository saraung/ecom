from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.models.coupon import Coupon, DiscountType
from app.core.region import format_money


def validate_coupon(
    coupon: Coupon,
    cart_subtotal: Decimal,
    user_id: UUID | None = None,
    user_usage_count: int = 0,
) -> tuple[bool, str]:
    """
    Validate coupon against cart and user.
    Returns: (is_valid, message)
    """
    
    # Check if coupon is active
    if not coupon.is_active:
        return False, "This coupon is currently inactive"

    # Internal/test codes can never be used on public orders.
    if getattr(coupon, "internal_only", False):
        return False, "This coupon code is not valid"
    
    # Check if coupon is valid from date
    if coupon.valid_from and coupon.valid_from > datetime.now():
        return False, f"This coupon will be available from {coupon.valid_from.strftime('%d %b %Y')}"
    
    # Check if coupon is expired
    if coupon.valid_until and coupon.valid_until < datetime.now():
        return False, f"This coupon expired on {coupon.valid_until.strftime('%d %b %Y')}"
    
    # Check if max uses reached
    if coupon.max_uses and coupon.times_used >= coupon.max_uses:
        return False, f"Sorry, this coupon has reached its maximum usage limit ({coupon.max_uses} uses)"
    
    # Check if user has exceeded per-user limit
    if user_id and coupon.max_uses_per_user and user_usage_count >= coupon.max_uses_per_user:
        return False, f"You have already used this coupon. Maximum {coupon.max_uses_per_user} use(s) per customer."
    
    # Check min order value
    if coupon.min_order_value and cart_subtotal < coupon.min_order_value:
        return False, f"Minimum order value of {format_money(coupon.min_order_value)} required. Current subtotal: {format_money(cart_subtotal)}"
    
    return True, "Coupon applied successfully!"


def calculate_discount(
    coupon: Coupon,
    cart_subtotal: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Calculate discount amount.
    Returns: (discount_amount, new_subtotal)
    """
    if coupon.discount_type == DiscountType.PERCENTAGE:
        discount_amount = cart_subtotal * (coupon.value / 100)
    else:  # FIXED
        discount_amount = coupon.value
    
    # Don't allow discount to exceed subtotal
    if discount_amount > cart_subtotal:
        discount_amount = cart_subtotal
    
    new_subtotal = cart_subtotal - discount_amount
    
    return discount_amount, new_subtotal


def generate_coupon_code(length: int = 8) -> str:
    """Generate a random coupon code"""
    import random
    import string
    
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choices(characters, k=length))