from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class ProductImageCreate(BaseModel):
    url: str = Field(max_length=500)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int = Field(default=0, ge=0)


class ProductImageUpdate(BaseModel):
    url: str | None = Field(default=None, max_length=500)
    alt_text: str | None = Field(default=None, max_length=255)
    sort_order: int | None = Field(default=None, ge=0)


class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_id: UUID
    url: str
    secure_url: str | None
    cloudinary_public_id: str | None
    alt_text: str | None
    sort_order: int
    created_at: datetime
