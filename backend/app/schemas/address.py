from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.region import default_country


class AddressCreate(BaseModel):
    label: str | None = None
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str = Field(default_factory=default_country)
    is_default: bool = Field(default=False)


class AddressUpdate(BaseModel):
    label: str | None = None
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    is_default: bool | None = None


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    user_id: UUID
    label: str | None = None  # ✅ THIS IS THE FIX - Added default None
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime