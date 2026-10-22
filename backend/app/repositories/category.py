from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Session

from app.models.category import Category
from app.models.product import Product
from app.schemas.category import CategoryCreate, CategoryUpdate


def get_categories(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    is_active: bool | None = None,
) -> list[Category]:
    statement = (
        select(Category)
        .order_by(Category.sort_order.asc(), Category.name.asc())
        .offset(skip)
        .limit(limit)
    )
    if is_active is not None:
        statement = statement.where(Category.is_active == is_active)
    result = session.execute(statement)
    return result.scalars().all()


def get_direct_product_counts(session: Session) -> dict[UUID, int]:
    """Direct (non-recursive) product count per category id, one query."""
    rows = session.execute(
        select(Product.category_id, func.count())
        .where(Product.category_id.is_not(None))
        .group_by(Product.category_id)
    ).all()
    return {category_id: count for category_id, count in rows}


def get_category_by_id(session: Session, category_id: UUID) -> Category | None:
    return session.get(Category, category_id)


def get_category_by_slug(session: Session, slug: str) -> Category | None:
    statement = select(Category).where(Category.slug == slug)
    result = session.execute(statement)
    return result.scalar_one_or_none()


def create_category(session: Session, category_data: CategoryCreate, *, commit: bool = True) -> Category:
    # exclude_none: unset optionals (image_url/is_active/sort_order) must
    # fall back to model defaults, not overwrite them with NULL.
    category = Category(**category_data.model_dump(exclude_none=True))
    session.add(category)
    if commit:
        session.commit()
        session.refresh(category)
    else:
        session.flush()
    return category


def update_category(session: Session, category: Category, category_data: CategoryUpdate, *, commit: bool = True) -> Category:
    update_data = category_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(category, field, value)

    session.add(category)
    if commit:
        session.commit()
        session.refresh(category)
    else:
        session.flush()
    return category


def delete_category(session: Session, category: Category, *, commit: bool = True) -> None:
    session.delete(category)
    session.commit() if commit else session.flush()
