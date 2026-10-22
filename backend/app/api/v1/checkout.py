from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session
from sqlalchemy import select

from app.api.deps import SessionDep,CurrentUser
from app.models.cart import Cart
from app.models.order import Order, OrderItem, OrderStatus
from app.models.product import ProductVariant
from app.models.user import User
from app.models.address import Address
from app.repositories import cart as cart_repo
from app.repositories import address as address_repo
from app.repositories import coupon as coupon_repo
from app.schemas.checkout import CheckoutConfigResponse, CheckoutRequest, OrderRead
from app.models.coupon import Coupon
from app.utils.cart import validate_cart_items
from app.services.pricing import resolve_cart_pricing
from app.utils.order import generate_order_number
from app.repositories import notification as notification_repo
from app.services.email_outbox import enqueue_order_email
from app.core.config import settings
from app.core.store_settings import get_store_settings
from app.core.region import format_money
from app.services.order_snapshot import customer_snapshot, address_snapshot


router = APIRouter(prefix="/checkout", tags=["Checkout"])


def _buyer_permissions(session, user) -> list[str]:
    """Dynamic permission union for the checkout buyer (empty for shoppers)."""
    try:
        from app.repositories import rbac as rbac_repo

        return rbac_repo.get_user_permissions(session, user.id)
    except Exception:
        legacy = getattr(user.role, "value", user.role) or "customer"
        return [] if str(legacy) == "customer" else [str(legacy)]


@router.get("/config", response_model=CheckoutConfigResponse)
def get_checkout_config(session: SessionDep = None):
    """
    Client-facing checkout pricing configuration (public — nothing sensitive).

    Production rule ("single source of truth"): these values are display-only
    hints so the storefront doesn't hardcode business rules like the COD fee
    or eligibility limits. The authoritative computation always happens
    server-side in `checkout()` below, which re-reads the same settings,
    re-applies the eligibility guards and persists `cod_fee` on the order row.
    """
    from app.core.region import (
        currency_code,
        default_country,
        display_locale,
        tax_label,
    )

    store = get_store_settings(session, seed=False)
    return CheckoutConfigResponse(
        cod_fee=store.cod_fee,
        cod_min_order_value=store.cod_min_order_value,
        cod_max_order_value=store.cod_max_order_value,
        free_shipping_threshold=store.free_shipping_threshold,
        shipping_cost=store.shipping_cost,
        tax_rate=store.tax_rate,
        currency=currency_code(),
        locale=display_locale(),
        tax_label=tax_label(),
        country=default_country(),
        support_phone=settings.STORE_SUPPORT_PHONE or "",
    )


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def checkout(
    checkout_data: CheckoutRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Place an order atomically; failed attempts leave the session reusable."""
    try:
        return _checkout(checkout_data, session, current_user)
    except Exception:
        session.rollback()
        raise


def _checkout(checkout_data: CheckoutRequest, session: Session, current_user: User):
    """
    Convert cart to order.
    """
    
    print("\n" + "="*50)
    print("=== CHECKOUT DEBUG START ===")
    print("="*50)
    
    # 1. Validate shipping address exists
    shipping_address = address_repo.get_address_by_id(
        session, checkout_data.shipping_address_id
    )
    if not shipping_address or shipping_address.user_id != current_user.id:
        raise HTTPException(
            status_code=400,
            detail="Invalid shipping address"
        )
    
    # 2. Handle billing address
    billing_address_id = checkout_data.billing_address_id
    if checkout_data.billing_address_id:
        billing_address = address_repo.get_address_by_id(
            session, checkout_data.billing_address_id
        )
        if not billing_address or billing_address.user_id != current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Invalid billing address"
            )
    else:
        billing_address_id = checkout_data.shipping_address_id
        billing_address = shipping_address
    
    # 3. Get user's cart
    # Serialize consumption of one cart. Never create/commit a cart during checkout.
    cart = session.execute(
        select(Cart).where(Cart.user_id == current_user.id)
        .with_for_update().execution_options(populate_existing=True)
    ).scalars().first()
    if cart is None:
        raise HTTPException(status_code=400, detail="Cart is empty")
    session.expire(cart, ["items"])
    cart_with_items = cart_repo.get_cart_with_items(session, cart.id)
    
    if not cart_with_items.items:
        raise HTTPException(
            status_code=400,
            detail="Cart is empty"
        )
    
    # 4. Validate stock
    validation = validate_cart_items(cart_with_items)
    if not validation["valid"]:
        raise HTTPException(
            status_code=400,
            detail="; ".join(validation["errors"])
        )
    
    # 5-9. Resolve pricing via the central engine (single source of truth).
    # The engine re-validates any manual coupon on the cart AND evaluates
    # automatic coupons against their trigger conditions — checkout is the
    # final authority on whether a discount applies and how large it is.
    pricing = resolve_cart_pricing(session, cart_with_items, current_user)
    subtotal = pricing.subtotal
    print(f"Subtotal: {subtotal}")
    
    winner = pricing.manual or pricing.automatic
    coupon_code = winner.coupon.code if winner else None
    discount_amount = pricing.discount_total
    final_subtotal = pricing.new_subtotal
    
    if winner:
        winner_kind = "automatic" if pricing.manual is None else "manual"
        print(
            f"Coupon applied ({winner_kind}): {coupon_code}, "
            f"discount={discount_amount}, new subtotal: {final_subtotal}"
        )
    
    if cart.coupon_code and pricing.manual is None:
        # Stored manual code is no longer valid — drop it from the cart.
        cart.coupon_code = None
        session.add(cart)
    
    tax_amount = pricing.tax_total
    print(f"Tax amount: {tax_amount}")
    
    shipping_amount = pricing.shipping_total
    print(f"Shipping amount: {shipping_amount}")
    
    grand_total = pricing.total
    print(f"Grand total: {grand_total}")
    
    # 9.5 Resolve payment method from checkout body (persisted on the order)
    payment_method = checkout_data.payment_method.value  # cod | online
    
    # 10. COD (Cash on Delivery) handling (store policy, session-fresh)
    # Startup owns seeding; a missing policy must not commit this transaction.
    store_policy = pricing.policy or get_store_settings(session, seed=False)
    cod_fee = Decimal("0.00")
    if payment_method == "cod":
        # Industry-standard eligibility guards
        if grand_total < Decimal(str(store_policy.cod_min_order_value)):
            raise HTTPException(
                status_code=400,
                detail=f"Cash on Delivery is available only for orders of {format_money(store_policy.cod_min_order_value)} or more",
            )
        if grand_total > Decimal(str(store_policy.cod_max_order_value)):
            raise HTTPException(
                status_code=400,
                detail=f"Cash on Delivery is available only for orders up to {format_money(store_policy.cod_max_order_value)}. Please pay online.",
            )
        cod_fee = Decimal(str(store_policy.cod_fee))
        grand_total += cod_fee
        print(f"COD order: fee={cod_fee}, payable on delivery={grand_total}")

    # 10. Create order
    order_number = generate_order_number()
    print(f"Order number: {order_number}")

    order = Order(
        order_number=order_number,
        user_id=current_user.id,
        shipping_address_id=checkout_data.shipping_address_id,
        billing_address_id=billing_address_id,
        customer_snapshot=customer_snapshot(current_user),
        shipping_snapshot=address_snapshot(shipping_address, current_user),
        billing_snapshot=address_snapshot(billing_address, current_user),
        subtotal=final_subtotal,
        discount_total=discount_amount,
        tax_total=tax_amount,
        shipping_total=shipping_amount,
        cod_fee=cod_fee,
        grand_total=grand_total,
        coupon_code=coupon_code,
        payment_method=payment_method,
        # Staff shopping on the storefront keep full customer rights, but
        # the order is flagged for guardrails (self-dealing block,
        # analytics/promo exclusion).
        placed_by_staff=bool(
            _buyer_permissions(session, current_user)
        ),
        # COD orders are confirmed immediately (cash collected on delivery);
        # prepaid orders wait for the payment intent flow
        status=OrderStatus.CONFIRMED if payment_method == "cod" else OrderStatus.PENDING,
        payment_status="cod_pending" if payment_method == "cod" else "pending",
    )
    session.add(order)
    session.flush()
    
    # 11. Create order items & decrement stock.
    # Variants are row-locked (FOR UPDATE) and re-checked inside this
    # transaction: cart validation ran earlier, and without the lock two
    # concurrent checkouts could both pass validation and drive stock
    # negative (classic oversell race).
    from sqlalchemy import select as _select_variant

    locked_variants = {
        v.id: v
        for v in session.execute(
            _select_variant(ProductVariant)
            .where(ProductVariant.id.in_(
                [item.variant_id for item in cart_with_items.items]
            ))
            .order_by(ProductVariant.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars().all()
    }
    for item in cart_with_items.items:
        variant = locked_variants.get(item.variant_id)
        if variant is None:
            raise HTTPException(
                status_code=400, detail="A product variant is no longer available"
            )
        if variant.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Only {variant.stock} left in stock for {variant.sku}",
            )
        product = variant.product
        
        order_item = OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            product_name=product.name,
            variant_sku=variant.sku,
            variant_attributes=variant.attributes,
            quantity=item.quantity,
            unit_price=item.price_at_add,
            line_total=item.price_at_add * item.quantity,
        )
        session.add(order_item)
        
        # Decrement stock
        variant.stock -= item.quantity
        session.add(variant)
    
    # 12. Clear cart
    cart_repo.clear_cart(session, cart_with_items, commit=False)
    
    # 12b. Record usage of the winning coupon (manual AND automatic).
    # Counted here at order placement — never at cart-apply time (abandoned
    # carts must not burn max_uses budget). Row-locked + re-checked so two
    # concurrent checkouts can't both consume the last use.
    if winner:
        from sqlalchemy import select as _select

        locked = session.execute(
            _select(Coupon)
            .where(Coupon.id == winner.coupon.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars().one()
        if locked.max_uses and locked.times_used >= locked.max_uses:
            raise HTTPException(
                status_code=400,
                detail="Sorry, this coupon just reached its maximum usage limit",
            )
        coupon_repo.increment_coupon_usage(session, locked, commit=False)
    
    # 13. Commit everything
    if payment_method == "cod":
        enqueue_order_email(session, order, "order_confirmation")
    session.commit()
    session.refresh(order)
    
    # 13b. Notify managers/admins about the new order (notifications feed)
    try:
        notification_repo.notify_admins_order_placed(session, order)
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Failed to create order notifications: {str(e)}")
    
    print("="*50)
    print(f"FINAL ORDER: payment_method={payment_method}, cod_fee={order.cod_fee}, coupon_code={order.coupon_code}, grand_total={order.grand_total}")
    print("=== CHECKOUT DEBUG END ===")
    print("="*50 + "\n")
    
    return order
