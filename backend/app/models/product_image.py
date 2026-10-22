from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel




class ProductImage(SQLModel, table=True):
    __tablename__ = "product_images"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    product_id: UUID = Field(foreign_key="products.id", index=True)
    url: str  # Backward-compatible alias for the delivery URL
    secure_url: str | None = Field(default=None, max_length=1000)
    cloudinary_public_id: str | None = Field(default=None, max_length=500, index=True)
    alt_text: str | None = None
    sort_order: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # Relationship
    product: "Product" = Relationship(back_populates="images")
