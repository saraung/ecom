from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from app.models.product import ProductVariant
from app.models.user import User


class Cart(SQLModel, table=True):
    __tablename__ = "carts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(
        default=None, 
        foreign_key="users.id", 
        index=True,
        unique=True  # One cart per user
    )
    session_id: str | None = Field(
        default=None, 
        index=True
    )
    coupon_code: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )

    # Relationships
    user: User | None = Relationship(back_populates="cart")
    items: list["CartItem"] = Relationship(back_populates="cart")


class CartItem(SQLModel, table=True):
    __tablename__ = "cart_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    cart_id: UUID = Field(foreign_key="carts.id", index=True)
    variant_id: UUID = Field(foreign_key="product_variants.id", index=True)
    quantity: int = Field(ge=1)
    price_at_add: Decimal = Field(max_digits=12, decimal_places=2)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    cart: Cart = Relationship(back_populates="items")
    variant: ProductVariant = Relationship(back_populates="cart_items")


class CartMergeReceipt(SQLModel, table=True):
    __tablename__ = "cart_merge_receipts"
    cart_id: UUID = Field(foreign_key="carts.id", primary_key=True, ondelete="CASCADE")
    merge_key: UUID = Field(primary_key=True)
    variant_id: UUID
    quantity: int
