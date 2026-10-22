"""
Central pricing engine — the single source of truth for cart discounts.

Every cart read/mutation and the checkout resolve their totals through
`resolve_cart_pricing()` so the backend is always the final authority on
whether a coupon (manual or automatic) applies and how much it is worth.
The storefront only renders what this engine decides — it never computes
discounts, taxes or totals itself.

Decision ladder (deterministic — exactly ONE winner per cart, no stacking):

  1. Base cart computation (subtotal, item count, shipping).
  2. Manual coupon resolution — `Cart.coupon_code` is re-validated
     (active, validity window, usage limits, min order value).
  3. Automatic coupon evaluation — every active AUTOMATIC coupon has its
     trigger checked against the base cart; eligible candidates get their
     discount computed.
  4. Precedence: a valid manual coupon always wins. With no manual
     coupon, the eligible automatic coupon with the highest discount
     wins; ties break on the newest coupon for determinism.
  5. Totals recomputation (tax on the post-discount subtotal at the
     configured TAX_RATE, shipping from the base cart rules).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlmodel import Session
from app.core.region import format_money

from app.core.config import settings
from app.models.cart import Cart
from app.models.coupon import Coupon, CouponType, TriggerType
from app.models.user import User
from app.repositories import coupon as coupon_repo
from app.schemas.cart import AutomaticCouponRead, CartRead
from app.utils.cart import calculate_cart_total
from app.utils.coupon import calculate_discount, validate_coupon
from app.core.store_settings import get_store_settings, StoreSettingsSnapshot


def _tax_rate() -> Decimal:
    """Store tax rate as Decimal (DB-backed, env fallback)."""
    from app.core.store_settings import get_store_settings

    return Decimal(str(get_store_settings().tax_rate))


def _enum_value(field) -> str:
    """Normalize enum members / plain strings to their value."""
    return str(getattr(field, "value", field))


@dataclass
class CouponDecision:
    """A coupon plus the discount amount it yields on the current cart."""

    coupon: Coupon
    discount_amount: Decimal


@dataclass
class CartPricing:
    """Full pricing result resolved by the engine."""

    subtotal: Decimal
    item_count: int
    items: list
    shipping_total: Decimal
    manual: CouponDecision | None
    automatic: CouponDecision | None
    discount_total: Decimal
    new_subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    policy: StoreSettingsSnapshot | None = None


def trigger_description(coupon: Coupon) -> str:
    """Human-readable trigger summary for the storefront / admin UI."""
    trigger = _enum_value(coupon.trigger_type)
    if trigger == TriggerType.MIN_CART_VALUE.value:
        return (
            f"Applies automatically to carts of {format_money(coupon.trigger_min_cart_value)} "
            "or more"
        )
    if trigger == TriggerType.MIN_ITEM_COUNT.value:
        return (
            f"Applies automatically to carts with "
            f"{coupon.trigger_min_item_count}+ items"
        )
    if trigger == TriggerType.CATEGORY_SPEND.value:
        return (
            f"Applies automatically when you spend "
            f"{format_money(coupon.trigger_category_spend)} in this category"
        )
    if trigger == TriggerType.FIRST_ORDER.value:
        return "Applies automatically on your first order"
    return "Applies automatically"


def _is_valid_for_user(
    session: Session,
    coupon: Coupon,
    subtotal: Decimal,
    user: User | None,
) -> bool:
    """Shared validity check: active, window, usage limits, min order value."""
    user_id = user.id if user else None
    user_usage_count = 0
    if user_id:
        user_usage_count = coupon_repo.get_user_coupon_usage_count(
            session, coupon.code, user_id
        )
    is_valid, _message = validate_coupon(coupon, subtotal, user_id, user_usage_count)
    return is_valid


def _resolve_manual(
    session: Session,
    cart_with_items: Cart,
    subtotal: Decimal,
    user: User | None,
) -> CouponDecision | None:
    """Validate the manually-applied coupon on the cart, if any.

    Automatic coupon codes can never sit in `Cart.coupon_code`, so anything
    stored there is treated as a manual code.
    """
    if not cart_with_items.coupon_code:
        return None

    coupon = coupon_repo.get_coupon_by_code(session, cart_with_items.coupon_code)
    if not coupon or _enum_value(coupon.coupon_type) == CouponType.AUTOMATIC.value:
        return None

    if not _is_valid_for_user(session, coupon, subtotal, user):
        return None

    discount_amount, _new_subtotal = calculate_discount(coupon, subtotal)
    return CouponDecision(coupon=coupon, discount_amount=discount_amount)


def _category_spend(cart_with_items: Cart, category_id) -> Decimal:
    """Sum of item totals whose product belongs to the given category."""
    spend = Decimal("0.00")
    for item in cart_with_items.items:
        product = item.variant.product if item.variant else None
        if product is not None and product.category_id == category_id:
            spend += item.price_at_add * item.quantity
    return spend


def _trigger_satisfied(
    session: Session,
    coupon: Coupon,
    cart_with_items: Cart,
    subtotal: Decimal,
    item_count: int,
    user: User | None,
) -> bool:
    """Check the coupon's trigger condition against the current cart."""
    trigger = _enum_value(coupon.trigger_type)

    if trigger == TriggerType.MIN_CART_VALUE.value:
        return (
            coupon.trigger_min_cart_value is not None
            and subtotal >= coupon.trigger_min_cart_value
        )

    if trigger == TriggerType.MIN_ITEM_COUNT.value:
        return (
            coupon.trigger_min_item_count is not None
            and item_count >= coupon.trigger_min_item_count
        )

    if trigger == TriggerType.CATEGORY_SPEND.value:
        if coupon.trigger_category_id is None or coupon.trigger_category_spend is None:
            return False
        return (
            _category_spend(cart_with_items, coupon.trigger_category_id)
            >= coupon.trigger_category_spend
        )

    if trigger == TriggerType.FIRST_ORDER.value:
        if user is None:
            return False
        return coupon_repo.get_completed_order_count(session, user.id) == 0

    return False


def evaluate_automatic_coupons(
    session: Session,
    cart_with_items: Cart,
    subtotal: Decimal,
    item_count: int,
    user: User | None,
) -> CouponDecision | None:
    """
    Evaluate every active AUTOMATIC coupon against the cart and return the
    single best eligible one (highest discount; ties break on the newest
    coupon for determinism), or None.

    Automatic coupons require an authenticated user so first-order and
    per-user usage conditions can be enforced server-side.
    """
    if user is None:
        return None

    candidates: list[CouponDecision] = []
    for coupon in coupon_repo.get_active_automatic_coupons(session):
        if not _is_valid_for_user(session, coupon, subtotal, user):
            continue
        if not _trigger_satisfied(
            session, coupon, cart_with_items, subtotal, item_count, user
        ):
            continue
        discount_amount, _new_subtotal = calculate_discount(coupon, subtotal)
        candidates.append(CouponDecision(coupon=coupon, discount_amount=discount_amount))

    if not candidates:
        return None

    candidates.sort(
        key=lambda d: (d.discount_amount, d.coupon.created_at, d.coupon.id),
        reverse=True,
    )
    return candidates[0]


def resolve_cart_pricing(
    session: Session,
    cart_with_items: Cart,
    user: User | None,
) -> CartPricing:
    """Run the full decision ladder and return the authoritative pricing."""
    policy = get_store_settings(session, seed=False)
    base = calculate_cart_total(cart_with_items, policy=policy)
    subtotal = base["subtotal"]
    item_count = base["item_count"]

    # Step 2 — manual coupon on the cart (re-validated every time).
    manual = _resolve_manual(session, cart_with_items, subtotal, user)

    # Step 3 — automatic coupons only when no manual code wins, and only on
    # a non-empty cart (nothing can 'apply itself' to an empty cart).
    automatic = None
    if manual is None and cart_with_items.items:
        automatic = evaluate_automatic_coupons(
            session, cart_with_items, subtotal, item_count, user
        )

    # Step 4 — precedence: exactly one winner.
    winner = manual or automatic
    discount_total = winner.discount_amount if winner else Decimal("0.00")

    # Step 5 — totals on the discounted amount.
    new_subtotal = subtotal - discount_total
    tax_total = new_subtotal * Decimal(str(policy.tax_rate))
    shipping_total = base["shipping_total"]
    total = new_subtotal + tax_total + shipping_total

    return CartPricing(
        subtotal=subtotal,
        item_count=item_count,
        items=base["items"],
        shipping_total=shipping_total,
        manual=manual,
        automatic=automatic,
        discount_total=discount_total,
        new_subtotal=new_subtotal,
        tax_total=tax_total,
        total=total,
        policy=policy,
    )


def build_cart_read(cart_with_items: Cart, pricing: CartPricing) -> CartRead:
    """Build the API cart response from the engine's decision."""
    automatic_coupon = None
    if pricing.automatic:
        c = pricing.automatic.coupon
        automatic_coupon = AutomaticCouponRead(
            code=c.code,
            discount_type=_enum_value(c.discount_type),
            value=c.value,
            discount_amount=pricing.automatic.discount_amount,
            trigger_type=_enum_value(c.trigger_type),
            description=trigger_description(c),
        )

    return CartRead(
        id=cart_with_items.id,
        items=pricing.items,
        subtotal=pricing.subtotal,
        # Keep returning the stored code even when it stopped being valid so
        # the UI pill stays visible; the discount simply isn't counted.
        coupon_code=cart_with_items.coupon_code,
        automatic_coupon=automatic_coupon,
        discount_total=pricing.discount_total,
        tax_total=pricing.tax_total,
        shipping_total=pricing.shipping_total,
        total=pricing.total,
        item_count=pricing.item_count,
    )
