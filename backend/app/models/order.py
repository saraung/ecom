# app/models/order.py
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4
from types import SimpleNamespace

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel


#: Customer-facing labels for every OrderStatus value (single source of truth).
#: Mirrors ORDER_STATUS_LABELS in the web apps, which render these strings.
_ORDER_STATUS_LABELS: dict[str, str] = {
    "pending": "Pending",
    "confirmed": "Confirmed",
    "processing": "Processing",
    "shipped": "Shipped",
    "out_for_delivery": "Out for Delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
    "rto": "Returned to Origin",
    "refunded": "Refunded",
}


class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RTO = "rto"
    REFUNDED = "refunded"

    @property
    def label(self) -> str:
        """Human-readable label for customer-facing copy ("out_for_delivery" -> "Out for Delivery")."""
        return _ORDER_STATUS_LABELS[self.value]


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_number: str = Field(unique=True, index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    
    # Addresses
    shipping_address_id: UUID = Field(foreign_key="addresses.id")
    billing_address_id: UUID = Field(foreign_key="addresses.id")
    # Immutable purchase-time data; foreign keys continue to establish ownership.
    customer_snapshot: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    shipping_snapshot: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    billing_snapshot: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    
    # 👇 ADD THESE TWO RELATIONSHIPS
    shipping_address: "Address" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[Order.shipping_address_id]",
            "primaryjoin": "Order.shipping_address_id == Address.id",
        }
    )
    billing_address: "Address" = Relationship(
        sa_relationship_kwargs={
            "foreign_keys": "[Order.billing_address_id]",
            "primaryjoin": "Order.billing_address_id == Address.id",
        }
    )
    
    # Financials
    subtotal: Decimal = Field(max_digits=12, decimal_places=2)
    discount_total: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    tax_total: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    shipping_total: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    grand_total: Decimal = Field(max_digits=12, decimal_places=2)
    
    # Coupon
    coupon_code: str | None = None
    
    # Coupon
    coupon_code: str | None = None
    
    # Payment
    payment_method: str | None = None  # 'cod' or 'online' (choice made at checkout)
    cod_fee: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    # Courier remittance (Shiprocket paying the merchant), separate from the
    # customer-facing collection recorded in ``payments``. Additive only:
    # ``payment_status`` keeps its existing meaning.
    cod_remitted_amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    cod_remittance_status: str = Field(default="pending", max_length=20, index=True)
    cod_remitted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    
    # Status
    # Status
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    payment_status: str = Field(default="pending")

    # Cancellation
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None

    # True when the buyer held any admin permission at checkout time.
    # Drives guardrails (self-dealing block, analytics exclusion) while the
    # account keeps full shopping rights.
    placed_by_staff: bool = Field(default=False, index=True)

    # Refund
    refund_amount: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    refund_id: str | None = None           # Razorpay refund ID (rfnd_xxx)
    refund_reason: str | None = None
    restocking_fee: Decimal = Field(default=0, max_digits=12, decimal_places=2)
    refunded_at: datetime | None = None

    # Shiprocket / Shipping Details
    shiprocket_order_id: str | None = Field(default=None, index=True)
    shiprocket_shipment_id: str | None = Field(default=None, index=True)
    awb_code: str | None = Field(default=None, index=True)
    courier_name: str | None = None
    courier_id: int | None = None
    # Courier ETD text captured at dispatch ("3-4 Days").
    # Drives the customer-facing "Arriving by …" date.
    courier_etd: str | None = None
    expected_delivery_date: datetime | None = None
    shipping_label_url: str | None = None
    manifest_url: str | None = None
    shipment_status: str | None = None
    pickup_scheduled_date: datetime | None = None
    tracking_data: list[dict] | dict | None = Field(
        default=None,
        sa_column=Column(JSON, nullable=True)
    )

    # RTO restock guard: a parcel handed back to the seller must restore
    # stock EXACTLY once. Webhooks retry and RTO scans arrive in stages
    # (INITIATED then DELIVERED), so "did the status just change" is not a
    # sufficient condition — this flag is.
    rto_stock_restored: bool = Field(default=False, index=True)
    stock_released: bool = Field(default=False)

    # Timestamps
    placed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)}
    )
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None

    # Relationships - use string references to avoid circular imports
    user: "User" = Relationship(back_populates="orders")
    items: list["OrderItem"] = Relationship(back_populates="order")
    payments: list["Payment"] = Relationship(back_populates="order")
    reviews: list["Review"] = Relationship(back_populates="order")

    # ---------------------------------------------------------
    # Computed helpers (not DB columns)
    # ---------------------------------------------------------
    @property
    def customer_details(self):
        return SimpleNamespace(**self.customer_snapshot) if self.customer_snapshot is not None else self.user

    @property
    def shipping_details(self):
        return SimpleNamespace(**self.shipping_snapshot) if self.shipping_snapshot is not None else self.shipping_address

    @property
    def billing_details(self):
        return SimpleNamespace(**self.billing_snapshot) if self.billing_snapshot is not None else self.billing_address

    @property
    def succeeded_payment(self):
        """The payment that captured money for this order (None if never paid).

        Matches `succeeded` and `refunded` payments — a refunded payment was
        still a real transaction, so it keeps an identifiable transaction ID.
        """
        for payment in self.payments or []:
            status = getattr(payment, "status", None)
            value = getattr(status, "value", status)
            if value in ("succeeded", "refunded"):
                return payment
        return None

    @property
    def transaction_id(self) -> str | None:
        """Razorpay transaction ID (pay_xxx) for a paid order.

        Resolves from the succeeded payment record: prefers the provider
        payment intent (pay_xxx) and falls back to the provider payment /
        order ID (order_xxx, or dummy_pay_xxx in dev).
        """
        payment = self.succeeded_payment
        if payment is None:
            return None
        return payment.provider_payment_intent or payment.provider_payment_id

    @property
    def can_cancel(self) -> bool:
        """Orders can be cancelled while PENDING, CONFIRMED or PROCESSING."""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
        )

    @property
    def can_refund(self) -> bool:
        """Refund is possible only for paid online orders not fully refunded."""
        if self.payment_method == "cod" or self.payment_status not in ("paid", "refund_failed"):
            return False
        already_refunded = self.refund_amount or Decimal(0)
        return already_refunded < self.grand_total - (self.restocking_fee or Decimal(0))

    @property
    def restocking_fee_percentage(self) -> float:
        """Restocking fee % based on the order status at cancellation time."""
        from app.core.store_settings import get_store_settings

        from sqlalchemy.orm import object_session
        store = get_store_settings(object_session(self), seed=False)
        if self.status == OrderStatus.PROCESSING:
            return store.restocking_fee_processing
        if self.status == OrderStatus.CONFIRMED:
            return store.restocking_fee_confirmed
        return store.restocking_fee_pending


class OrderItem(SQLModel, table=True):
    __tablename__ = "order_items"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id", index=True)
    variant_id: UUID = Field(foreign_key="product_variants.id", index=True)
    
    # Snapshot
    product_name: str
    variant_sku: str
    
    # Use sa_column=Column(JSON) for dict type
    variant_attributes: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False)
    )
    
    quantity: int
    unit_price: Decimal = Field(max_digits=12, decimal_places=2)
    line_total: Decimal = Field(max_digits=12, decimal_places=2)
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships - use string references
    order: "Order" = Relationship(back_populates="items")
    variant: "ProductVariant" = Relationship(back_populates="order_items")
