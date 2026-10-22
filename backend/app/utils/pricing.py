from decimal import Decimal

from app.models.product import Product, ProductVariant


def get_effective_price(
    product: Product,
    variant: ProductVariant | None = None
) -> Decimal:
    if variant and variant.price_override:
        return variant.price_override
    return product.price


def get_discount_percentage(
    product: Product,
    variant: ProductVariant | None = None
) -> int:
    price = get_effective_price(product, variant)
    
    if product.compare_at_price and product.compare_at_price > price:
        discount = product.compare_at_price - price
        percentage = (discount / product.compare_at_price) * 100
        return round(percentage)
    return 0


def get_savings_amount(
    product: Product,
    variant: ProductVariant | None = None
) -> Decimal:
    price = get_effective_price(product, variant)
    
    if product.compare_at_price and product.compare_at_price > price:
        return product.compare_at_price - price
    return Decimal("0.00")


def get_product_pricing_data(
    product: Product
) -> dict:
    return {
        "price": product.price,
        "compare_at_price": product.compare_at_price,
        "discount_percentage": get_discount_percentage(product),
        "savings_amount": get_savings_amount(product),
        "is_on_sale": product.compare_at_price is not None and 
                     product.compare_at_price > product.price
    }


def get_variant_pricing_data(
    product: Product,
    variant: ProductVariant
) -> dict:
    effective_price = get_effective_price(product, variant)
    
    return {
        "price": product.price,
        "compare_at_price": product.compare_at_price,
        "effective_price": effective_price,
        "price_override": variant.price_override,
        "discount_percentage": get_discount_percentage(product, variant),
        "savings_amount": get_savings_amount(product, variant),
        "is_on_sale": product.compare_at_price is not None and 
                     product.compare_at_price > effective_price
    }