from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from app.models.cart import Cart, CartItem, CartMergeReceipt
from app.models.coupon import CouponType
from app.models.product import ProductVariant
from app.models.product_image import ProductImage


def get_or_create_cart(
    session: Session,
    user_id: UUID | None = None,
    session_id: str | None = None
) -> Cart:
    """Get existing cart or create a new one"""
    
    if user_id:
        statement = (
            select(Cart)
            .where(Cart.user_id == user_id)
            .options(selectinload(Cart.items))
        )
        cart = session.exec(statement).first()
        if cart:
            return cart
    
    if session_id:
        statement = (
            select(Cart)
            .where(Cart.session_id == session_id)
            .options(selectinload(Cart.items))
        )
        cart = session.exec(statement).first()
        if cart:
            if user_id and not cart.user_id:
                cart.user_id = user_id
                cart.session_id = None
                session.add(cart)
                session.commit()
                session.refresh(cart)
            return cart
    
    cart = Cart(
        user_id=user_id,
        session_id=session_id if not user_id else None
    )
    session.add(cart)
    session.commit()
    session.refresh(cart)
    return cart


def get_cart_with_items(session: Session, cart_id: UUID) -> Cart | None:
    """Get cart with all relationships eagerly loaded."""
    
    # Load cart with items, variants, and products
    statement = (
        select(Cart)
        .where(Cart.id == cart_id)
        .options(
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
        )
    )
    cart = session.exec(statement).first()
    
    if cart:
        # Load images separately
        product_ids = []
        for item in cart.items:
            if item.variant and item.variant.product:
                product_ids.append(item.variant.product.id)
        
        if product_ids:
            images_stmt = select(ProductImage).where(
                ProductImage.product_id.in_(product_ids)
            ).order_by(ProductImage.sort_order.asc())
            images = session.exec(images_stmt).all()
            
            images_by_product = {}
            for image in images:
                if image.product_id not in images_by_product:
                    images_by_product[image.product_id] = []
                images_by_product[image.product_id].append(image)
            
            for item in cart.items:
                if item.variant and item.variant.product:
                    item.variant.product.images = images_by_product.get(
                        item.variant.product.id, []
                    )
    
    return cart


def add_item_to_cart(
    session: Session,
    cart: Cart,
    variant_id: UUID,
    quantity: int,
    *, commit: bool = True,
) -> CartItem:
    """Add item to cart or update quantity if exists."""
    
    variant = session.get(ProductVariant, variant_id, populate_existing=True)
    if not variant:
        raise ValueError("Variant not found")
    
    if variant.stock < quantity:
        raise ValueError(f"Only {variant.stock} items available")
    
    statement = select(CartItem).where(
        CartItem.cart_id == cart.id,
        CartItem.variant_id == variant_id
    ).execution_options(populate_existing=True)
    existing_item = session.exec(statement).first()
    
    if existing_item:
        new_quantity = existing_item.quantity + quantity
        if variant.stock < new_quantity:
            raise ValueError(f"Only {variant.stock} items available")
        existing_item.quantity = new_quantity
        session.add(existing_item)
        if commit:
            session.commit()
            session.refresh(existing_item)
        else:
            session.flush()
        return existing_item
    
    price = variant.price_override or variant.product.price
    cart_item = CartItem(
        cart_id=cart.id,
        variant_id=variant_id,
        quantity=quantity,
        price_at_add=price
    )
    
    session.add(cart_item)
    if commit:
        session.commit()
        session.refresh(cart_item)
    else:
        session.flush()
    return cart_item


def merge_cart_item(session: Session, cart: Cart, variant_id: UUID, quantity: int, merge_key: UUID):
    """An acknowledged guest entry is additive exactly once, even after a lost response."""
    try:
        session.exec(select(Cart).where(Cart.id == cart.id).with_for_update()).one()
        receipt = session.get(CartMergeReceipt, (cart.id, merge_key))
        if receipt is not None:
            if receipt.variant_id != variant_id or receipt.quantity != quantity:
                raise ValueError("Merge key was already used for a different cart entry")
            return
        add_item_to_cart(session, cart, variant_id, quantity, commit=False)
        session.add(CartMergeReceipt(cart_id=cart.id, merge_key=merge_key,
                                    variant_id=variant_id, quantity=quantity))
        session.commit()
    except Exception:
        session.rollback()
        raise


def update_cart_item(
    session: Session,
    cart_item: CartItem,
    quantity: int
) -> CartItem | None:
    """Update cart item quantity."""
    
    if quantity <= 0:
        session.delete(cart_item)
        session.commit()
        return None
    
    variant = session.get(ProductVariant, cart_item.variant_id)
    if variant and variant.stock < quantity:
        raise ValueError(f"Only {variant.stock} items available")
    
    cart_item.quantity = quantity
    session.add(cart_item)
    session.commit()
    session.refresh(cart_item)
    return cart_item


def remove_cart_item(session: Session, cart_item: CartItem) -> None:
    """Remove item from cart."""
    session.delete(cart_item)
    session.commit()


def clear_cart(session: Session, cart: Cart, *, commit: bool = True) -> None:
    """Clear the cart; checkout stages this in its caller-owned transaction."""
    statement = select(CartItem).where(CartItem.cart_id == cart.id)
    items = session.exec(statement).all()
    for item in items:
        session.delete(item)
    
    # Clear coupon code from cart
    cart.coupon_code = None
    session.add(cart)
    if commit:
        session.commit()
    else:
        session.flush()


def apply_coupon_to_cart(
    session: Session,
    cart: Cart,
    coupon_code: str,
) -> dict:
    """Apply coupon to cart"""
    from app.repositories import coupon as coupon_repo
    from app.utils.coupon import validate_coupon, calculate_discount
    
    # Get coupon
    coupon = coupon_repo.get_coupon_by_code(session, coupon_code)
    if not coupon:
        raise ValueError("Coupon not found")
    
    # Automatic coupons apply themselves — they cannot be typed in as codes
    if coupon.coupon_type == CouponType.AUTOMATIC:
        raise ValueError(
            "This coupon is applied automatically and cannot be entered as a code"
        )
    
    # Calculate cart subtotal
    subtotal = sum(item.price_at_add * item.quantity for item in cart.items)
    
    # 👇 Check user usage before applying
    user_usage_count = 0
    if cart.user_id:
        user_usage_count = coupon_repo.get_user_coupon_usage_count(
            session, coupon_code, cart.user_id
        )
    
    # Validate coupon (now checks max_uses_per_user)
    is_valid, message = validate_coupon(
        coupon, 
        subtotal, 
        cart.user_id,
        user_usage_count
    )
    if not is_valid:
        raise ValueError(message)
    
    # Calculate discount
    discount_amount, new_subtotal = calculate_discount(coupon, subtotal)
    
    # Apply coupon to cart
    cart.coupon_code = coupon_code

    # NOTE: usage is counted at CHECKOUT (order placement), not here. Counting
    # at apply time burns max_uses budget on abandoned carts (and checkout
    # counted again → double-count). Per-user limits are order-based and
    # unaffected.
    session.add(cart)
    session.commit()
    session.refresh(cart)
    
    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "new_subtotal": new_subtotal,
    }


def remove_coupon_from_cart(
    session: Session,
    cart: Cart,
) -> Cart:
    """Remove coupon from cart"""
    cart.coupon_code = None
    session.add(cart)
    session.commit()
    session.refresh(cart)
    return cart
