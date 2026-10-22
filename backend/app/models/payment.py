from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON  # 👈 Add this import
from sqlmodel import Field, Relationship, SQLModel


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, Enum):
    DUMMY = "dummy"
    RAZORPAY = "razorpay"
    STRIPE = "stripe"
    COD = "cod"  # Cash on Delivery (cash collected offline on delivery)


class Payment(SQLModel, table=True):
    __tablename__ = "payments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    
    provider: PaymentProvider = Field(default=PaymentProvider.DUMMY)
    provider_payment_id: str = Field(index=True)
    provider_payment_intent: str | None = None
    
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    currency: str = Field(default="INR")
    
    status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    
    payment_method: str | None = None
    last_four: str | None = None
    
    # 👇 Fix: Use different name and Column(JSON)
    payment_metadata: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False)
    )
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    
    # Relationship
    order: "Order" = Relationship(back_populates="payments")

    @property
    def transaction_id(self) -> str | None:
        """Payment transaction ID: the pay_xxx once captured, else the order id."""
        return self.provider_payment_intent or self.provider_payment_id