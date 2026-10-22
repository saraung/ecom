from uuid import UUID

from sqlmodel import Session, select

from app.models.product import Product
from app.models.product_image import ProductImage
from app.schemas.product_image import ProductImageCreate, ProductImageUpdate


def get_product_images(
    session: Session,
    product_id: UUID,
) -> list[ProductImage]:
    """Get all images for a product, ordered by sort_order"""
    
    statement = (
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.sort_order.asc())
    )
    return session.exec(statement).all()


def get_first_images_for_products(
    session: Session,
    product_ids: list[UUID],
) -> dict[UUID, str]:
    """Map product_id -> first image URL (lowest sort_order) for the given products"""
    
    if not product_ids:
        return {}
    
    statement = (
        select(ProductImage)
        .where(ProductImage.product_id.in_(product_ids))
        .order_by(ProductImage.sort_order.asc())
    )
    images = session.exec(statement).all()
    
    first_by_product: dict[UUID, str] = {}
    for image in images:
        first_by_product.setdefault(image.product_id, image.url)
    
    return first_by_product


def get_image_by_id(
    session: Session,
    image_id: UUID,
) -> ProductImage | None:
    """Get a single image by ID"""
    
    return session.get(ProductImage, image_id)


def create_product_image(
    session: Session,
    product_id: UUID,
    image_data: ProductImageCreate,
) -> ProductImage:
    """Add an image to a product"""
    
    # Verify product exists
    product = session.get(Product, product_id)
    if not product:
        raise ValueError("Product not found")
    
    image = ProductImage(
        product_id=product_id,
        **image_data.model_dump()
    )
    
    session.add(image)
    session.commit()
    session.refresh(image)
    
    return image


def update_product_image(
    session: Session,
    image: ProductImage,
    image_data: ProductImageUpdate,
) -> ProductImage:
    """Update an image"""
    
    update_data = image_data.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(image, field, value)
    
    session.add(image)
    session.commit()
    session.refresh(image)
    
    return image


def delete_product_image(
    session: Session,
    image: ProductImage,
) -> None:
    """Delete an image"""
    
    session.delete(image)
    session.commit()


def reorder_product_images(
    session: Session,
    product_id: UUID,
    image_ids: list[UUID],
) -> list[ProductImage]:
    """Reorder images for a product"""
    
    images = get_product_images(session, product_id)
    
    # Create mapping of image_id to sort_order
    order_map = {str(img_id): index for index, img_id in enumerate(image_ids)}
    
    for image in images:
        if str(image.id) in order_map:
            image.sort_order = order_map[str(image.id)]
            session.add(image)
    
    session.commit()
    
    # Return reordered list
    return get_product_images(session, product_id)