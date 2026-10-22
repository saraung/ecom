from datetime import datetime, timezone
from enum import Enum
import uuid

from sqlmodel import SQLModel, Field, Relationship


class UserRole(str, Enum):
    customer = "customer"
    staff = "staff"
    manager = "manager"
    admin = "admin"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, nullable=False)
    username: str = Field(unique=True, index=True, nullable=False)
    password_hash: str | None = Field(default=None, nullable=True)  # 👈 Made nullable
    role: UserRole = Field(default=UserRole.customer, index=True)
    full_name: str | None = None
    phone: str | None = None
    is_active: bool = Field(default=True)
    token_version: int = Field(default=0)
    email_verified: bool = Field(default=False)
    
    # Google OAuth fields
    google_id: str | None = Field(default=None, unique=True, index=True)
    auth_provider: str = Field(default="email")  # email, google, both

    # Notification preferences
    push_notifications_enabled: bool = Field(default=True)
    email_notifications_enabled: bool = Field(default=True)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    cart: "Cart" = Relationship(
        back_populates="user", 
        sa_relationship_kwargs={"uselist": False}
    )
    addresses: list["Address"] = Relationship(back_populates="user")
    orders: list["Order"] = Relationship(back_populates="user")
    reviews: list["Review"] = Relationship(back_populates="user")
    wishlist: list["Wishlist"] = Relationship(back_populates="user")
    coupons: list["Coupon"] = Relationship(back_populates="creator")
