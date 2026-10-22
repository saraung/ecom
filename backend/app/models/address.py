from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, Relationship, SQLModel

from app.core.region import default_country


class Address(SQLModel, table=True):
    __tablename__ = "addresses"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    
    label: str | None = None
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str = Field(default_factory=default_country)
    is_default: bool = Field(default=False)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # Relationship - use string reference
    user: "User" = Relationship(back_populates="addresses")