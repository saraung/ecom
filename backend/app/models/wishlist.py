from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel


class Wishlist(SQLModel, table=True):
    __tablename__ = "wishlists"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    user: "User" = Relationship(back_populates="wishlist")
    product: "Product" = Relationship(back_populates="wishlist")