from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
import io

from app.api.deps import SessionDep, require_perm
from app.repositories import audit as audit_repo
from app.models.user import User
from app.repositories import category as category_repo
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.services.cloudinary_service import (
    upload_image,
    delete_image as delete_cloudinary_image,
)

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.get("", response_model=list[CategoryRead])
def get_categories(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    is_active: bool | None = None,
):
    """Get all categories (direct product counts included).

    `is_active` is opt-in so existing callers (incl. the admin list) keep
    seeing everything; storefronts pass `is_active=true` to hide hidden
    categories.
    """
    categories = category_repo.get_categories(session, skip=skip, limit=limit, is_active=is_active)
    counts = category_repo.get_direct_product_counts(session)
    return [
        CategoryRead(
            id=c.id,
            name=c.name,
            slug=c.slug,
            parent_id=c.parent_id,
            created_at=c.created_at,
            image_url=c.image_url,
            is_active=c.is_active,
            sort_order=c.sort_order or 0,
            product_count=counts.get(c.id, 0),
        )
        for c in categories
    ]


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(
    category_id: UUID,
    session: SessionDep,
):
    """Get a category by ID."""
    category = category_repo.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    category_data: CategoryCreate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("categories.manage")),
):
    """Create a category."""
    existing = category_repo.get_category_by_slug(session, category_data.slug)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists")

    category = category_repo.create_category(session, category_data, commit=False)
    audit_repo.log_and_commit(
        session, action="category.created", entity="category",
        entity_id=category.id, actor_id=current_user.id,
        after={"name": category.name, "slug": category.slug},
        ip_address=audit_repo.client_ip(request),
    )
    return category


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: UUID,
    category_data: CategoryUpdate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("categories.manage")),
):
    """Update a category."""
    category = category_repo.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    if category_data.slug and category_data.slug != category.slug:
        existing = category_repo.get_category_by_slug(session, category_data.slug)
        if existing and existing.id != category.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category slug already exists")

    before = {"name": category.name, "slug": category.slug}
    updated = category_repo.update_category(session, category, category_data, commit=False)
    audit_repo.log_and_commit(
        session, action="category.updated", entity="category",
        entity_id=category.id, actor_id=current_user.id,
        before=before,
        after={"name": updated.name, "slug": updated.slug},
        ip_address=audit_repo.client_ip(request),
    )
    return updated


@router.post("/{category_id}/image/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_category_image(
    category_id: UUID,
    session: SessionDep,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_perm("categories.manage")),
):
    """Upload a category thumbnail to Cloudinary (`com/categories/{id}`).

    Sets `image_url` on the category; a previous Cloudinary asset for this
    category is removed so re-uploads don't orphan files (best-effort).
    Plain image URLs can still be pasted via PUT — both feed the same field.
    """
    category = category_repo.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
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

    uploaded = upload_image(blob, folder=f"com/categories/{category_id}", filename=file.filename)
    if not uploaded.get("secure_url") or not uploaded.get("public_id"):
        delete_cloudinary_image(uploaded.get("public_id"))
        raise HTTPException(status_code=502, detail="Cloudinary returned incomplete image metadata")

    previous_public_id = category.image_public_id
    category.image_url = uploaded["secure_url"]
    category.image_public_id = uploaded["public_id"]
    session.add(category)
    audit_repo.log_and_commit(
        session, action="category.updated", entity="category",
        entity_id=category.id, actor_id=current_user.id,
        after={"name": category.name, "image_url": category.image_url},
        ip_address=audit_repo.client_ip(request),
    )
    # Best-effort: never fail the request over stale-asset cleanup.
    if previous_public_id and previous_public_id != uploaded["public_id"]:
        delete_cloudinary_image(previous_public_id)
    return {"image_url": category.image_url, "image_public_id": category.image_public_id}


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("categories.manage")),
):
    """Delete a category."""
    category = category_repo.get_category_by_id(session, category_id)
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    snapshot = {"name": category.name, "slug": category.slug}
    category_repo.delete_category(session, category, commit=False)
    audit_repo.log_and_commit(
        session, action="category.deleted", entity="category",
        entity_id=category_id, actor_id=current_user.id,
        before=snapshot,
        ip_address=audit_repo.client_ip(request),
    )
    return None
