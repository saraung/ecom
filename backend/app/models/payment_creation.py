from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel


class PaymentCreation(SQLModel, table=True):
    __tablename__ = "payment_creations"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", unique=True)
    provider: str
    currency: str
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    payment_method: str
    state: str = Field(default="prepared")  # prepared -> submitting -> ready
    response: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                                sa_column=Column(DateTime(timezone=True), nullable=False))

    @property
    def creation_key(self):
        return f"pa-{self.id}"
