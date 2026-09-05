import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class Customer(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "customers"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    first_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_spend: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    order_count: Mapped[int] = mapped_column(Integer, default=0)


class CustomerSegment(Base, UUIDPKMixin):
    __tablename__ = "customer_segments"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))  # champions, loyal, at_risk, dormant, etc.
    label: Mapped[str] = mapped_column(String(255))
    definition_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class CustomerSegmentMembership(Base, UUIDPKMixin):
    __tablename__ = "customer_segment_memberships"

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    segment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_segments.id"), index=True)
    rfm_recency: Mapped[int] = mapped_column(Integer)
    rfm_frequency: Mapped[int] = mapped_column(Integer)
    rfm_monetary: Mapped[int] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
