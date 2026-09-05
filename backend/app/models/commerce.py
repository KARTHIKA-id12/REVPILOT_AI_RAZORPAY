import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class Cart(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "carts"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    session_ref: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active | abandoned | converted


class CartItem(Base, UUIDPKMixin):
    __tablename__ = "cart_items"

    cart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("carts.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_amount: Mapped[float] = mapped_column(Numeric(12, 2))


class Order(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "orders"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    cart_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("carts.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|paid|failed|cancelled|refunded
    subtotal_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    shipping_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    source: Mapped[str] = mapped_column(String(30), default="direct")  # merchant_campaign|ai_buyer|direct


class OrderItem(Base, UUIDPKMixin):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_amount: Mapped[float] = mapped_column(Numeric(12, 2))


class Payment(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_idempotency_key"),
        UniqueConstraint("provider_payment_link_id", name="uq_payment_provider_payment_link_id"),
        UniqueConstraint("provider_order_id", name="uq_payment_provider_order_id"),
    )

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(30))  # razorpay | mock
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_payment_link_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="created")  # created|paid|failed
    idempotency_key: Mapped[str] = mapped_column(String(255))


class PaymentEvent(Base, UUIDPKMixin):
    __tablename__ = "payment_events"

    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    raw_status: Mapped[str] = mapped_column(String(50))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
