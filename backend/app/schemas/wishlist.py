from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WishlistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    product_id: UUID
    created_at: datetime
    
    # Product details (optional)
    product_name: str | None = None
    product_slug: str | None = None
    product_price: str | None = None
    product_image: str | None = None


class WishlistResponse(BaseModel):
    items: list[WishlistItemRead]
    total: int