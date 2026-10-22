from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status
from sqlmodel import Session
from PIL import Image, UnidentifiedImageError
import io

from app.api.deps import SessionDep, require_perm
from app.repositories import product_image as image_repo
from app.repositories import product as product_repo
from app.models.user import User
from app.models.product_image import ProductImage
from app.schemas.product_image import (
    ProductImageCreate,
    ProductImageRead,
    ProductImageUpdate,
)
from app.services.cloudinary_service import delete_image as delete_cloudinary_image, upload_image

router = APIRouter(
    prefix="/products/{product_id}/images",
    tags=["Product Images"],
)


@router.get("", response_model=list[ProductImageRead])
def get_images(
    product_id: UUID,
    session: SessionDep,
):
    """Get all images for a product"""
    
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return image_repo.get_product_images(session, product_id)


@router.post("", response_model=ProductImageRead, status_code=status.HTTP_201_CREATED)
def add_image(
    product_id: UUID,
    image_data: ProductImageCreate,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("product_images.manage")
    ),
):
    """Add an image to a product"""
    
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    try:
        return image_repo.create_product_image(session, product_id, image_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/upload", response_model=ProductImageRead, status_code=status.HTTP_201_CREATED)
async def upload_product_image(
    product_id: UUID,
    session: SessionDep,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None, max_length=255),
    current_user: User = Depends(require_perm("product_images.manage")),
):
    """Upload a product image to Cloudinary under the product's folder."""
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    if file.content_type not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, WebP or GIF images are accepted")
    blob = await file.read(10 * 1024 * 1024 + 1)
    if len(blob) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")
    try:
        with Image.open(io.BytesIO(blob)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=415, detail="File is not a readable image") from exc

    uploaded = upload_image(blob, folder=f"com/products/{product_id}", filename=file.filename)
    if not uploaded.get("secure_url") or not uploaded.get("public_id"):
        delete_cloudinary_image(uploaded.get("public_id"))
        raise HTTPException(status_code=502, detail="Cloudinary returned incomplete image metadata")
    try:
        image = ProductImage(
            product_id=product_id,
            url=uploaded["secure_url"],
            secure_url=uploaded["secure_url"],
            cloudinary_public_id=uploaded["public_id"],
            alt_text=(alt_text or "").strip() or None,
            sort_order=len(image_repo.get_product_images(session, product_id)),
        )
        session.add(image)
        session.commit()
        session.refresh(image)
        return image
    except Exception:
        session.rollback()
        delete_cloudinary_image(uploaded["public_id"])
        raise


@router.put("/{image_id}", response_model=ProductImageRead)
def update_image(
    product_id: UUID,
    image_id: UUID,
    image_data: ProductImageUpdate,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("product_images.manage")
    ),
):
    """Update an image"""
    
    image = image_repo.get_image_by_id(session, image_id)
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    if image.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image does not belong to this product"
        )
    
    previous_public_id = image.cloudinary_public_id
    changed_url = image_data.url is not None and image_data.url != image.url
    if changed_url:
        image.secure_url = None
        image.cloudinary_public_id = None
    updated = image_repo.update_product_image(session, image, image_data)
    if changed_url:
        delete_cloudinary_image(previous_public_id)
    return updated


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    product_id: UUID,
    image_id: UUID,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("product_images.manage")
    ),
):
    """Delete an image"""
    
    image = image_repo.get_image_by_id(session, image_id)
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )
    
    if image.product_id != product_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image does not belong to this product"
        )
    
    public_id = image.cloudinary_public_id
    image_repo.delete_product_image(session, image)
    delete_cloudinary_image(public_id)


@router.post("/reorder", response_model=list[ProductImageRead])
def reorder_images(
    product_id: UUID,
    image_ids: list[UUID],
    session: SessionDep,
    current_user: User = Depends(
        require_perm("product_images.manage")
    ),
):
    """Reorder images for a product"""
    
    product = product_repo.get_product_by_id(session, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    return image_repo.reorder_product_images(session, product_id, image_ids)
