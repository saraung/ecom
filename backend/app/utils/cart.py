from decimal import Decimal
from typing import List

from app.core.store_settings import get_store_settings
from app.models.cart import Cart, CartItem
from app.models.product import ProductVariant


def calculate_item_total(cart_item: CartItem) -> Decimal:
    """
    Calculate total for a single cart item.
    
    Args:
        cart_item: CartItem object
        
    Returns:
        Decimal: Total price for this item (price * quantity)
    """
    return cart_item.price_at_add * cart_item.quantity


def calculate_subtotal(cart: Cart) -> Decimal:
    """
    Calculate subtotal of all items in cart.
    
    Args:
        cart: Cart object with items
        
    Returns:
        Decimal: Subtotal of all items
    """
    subtotal = Decimal("0.00")
    for item in cart.items:
        subtotal += calculate_item_total(item)
    return subtotal


def calculate_discount(cart: Cart) -> Decimal:
    """
    Calculate total discount from coupons.
    NOTE: This is a placeholder. Actual discount is calculated in API layer.
    """
    return Decimal("0.00")


def calculate_tax(cart: Cart, tax_rate: Decimal = None, *, policy=None) -> Decimal:
    """
    Calculate tax on cart total (after discount).
    
    Args:
        cart: Cart object
        tax_rate: Tax rate (default from config)
        
    Returns:
        Decimal: Tax amount
    """
    if tax_rate is None:
        tax_rate = Decimal(str((policy or get_store_settings()).tax_rate))
    
    subtotal = calculate_subtotal(cart)
    discount = calculate_discount(cart)
    taxable_amount = subtotal - discount
    return taxable_amount * tax_rate


def calculate_shipping(cart: Cart, free_shipping_threshold: Decimal = None, *, policy=None) -> Decimal:
    """
    Calculate shipping cost.
    
    Args:
        cart: Cart object
        free_shipping_threshold: Minimum amount for free shipping
        
    Returns:
        Decimal: Shipping cost
    """
    policy = policy or get_store_settings()
    if free_shipping_threshold is None:
        threshold = Decimal(str(policy.free_shipping_threshold))
    else:
        threshold = free_shipping_threshold
    
    subtotal = calculate_subtotal(cart)
    
    if subtotal == Decimal("0.00"):
        return Decimal("0.00")
    
    if subtotal >= threshold:
        return Decimal("0.00")
    
    shipping_cost = Decimal(str(policy.shipping_cost))
    return shipping_cost


def calculate_cart_total(cart: Cart, *, policy=None) -> dict:
    """
    Calculate all cart totals.
    
    Args:
        cart: Cart object with items
        
    Returns:
        dict: All calculated totals
    """
    subtotal = calculate_subtotal(cart)
    policy = policy or get_store_settings()
    discount = calculate_discount(cart)
    tax = calculate_tax(cart, policy=policy)
    shipping = calculate_shipping(cart, policy=policy)
    total = subtotal - discount + tax + shipping
    
    # Enrich items with product/variant data
    enriched_items = []
    for item in cart.items:
        variant = item.variant
        product = variant.product if variant else None
        product_image = product.images[0].url if product and product.images else None
        
        variant_attributes = variant.attributes if variant else None
        
        enriched_items.append({
            "id": item.id,
            "variant_id": item.variant_id,
            "quantity": item.quantity,
            "price_at_add": item.price_at_add,
            "created_at": item.created_at,
            "variant_sku": variant.sku if variant else None,
            "variant_attributes": variant_attributes,
            "product_name": product.name if product else None,
            "product_slug": product.slug if product else None,
            "product_image": product_image,
        })
    
    return {
        "subtotal": subtotal,
        "discount_total": discount,
        "tax_total": tax,
        "shipping_total": shipping,
        "total": total,
        "item_count": sum(item.quantity for item in cart.items),
        "items": enriched_items
    }


def validate_cart_items(cart: Cart) -> dict:
    """
    Validate all items in cart against current stock.
    
    Args:
        cart: Cart object with items
        
    Returns:
        dict: Validation results
    """
    errors = []
    warnings = []
    
    for item in cart.items:
        variant = item.variant
        if not variant:
            errors.append(f"Variant {item.variant_id} no longer exists")
            continue
            
        if variant.stock < item.quantity:
            errors.append(
                f"Not enough stock for {variant.sku}. Available: {variant.stock}, "
                f"Requested: {item.quantity}"
            )
        elif variant.stock < item.quantity * 2:
            warnings.append(
                f"Low stock for {variant.sku}. Only {variant.stock} left"
            )
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }
