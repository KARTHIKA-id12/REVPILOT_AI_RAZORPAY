import uuid
from datetime import timezone,  datetime
UTC = timezone.utc

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import UUIDPKMixin
from app.db.session import Base


class WebhookEvent(Base, UUIDPKMixin):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_webhook_event_id"),)

    provider: Mapped[str] = mapped_column(String(30))
    event_id: Mapped[str] = mapped_column(String(255))  # provider's unique event id -> idempotency key
    event_type: Mapped[str] = mapped_column(String(100))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signature_valid: Mapped[bool] = mapped_column(Boolean)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)


class RevenueAttribution(Base, UUIDPKMixin):
    __tablename__ = "revenue_attributions"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"))
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id"))
    attribution_type: Mapped[str] = mapped_column(String(30))  # campaign | ai_buyer | direct | estimated_incremental
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    attribution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base, UUIDPKMixin):
    __tablename__ = "audit_logs"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    agent_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))
    tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    permission_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_requests.id"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(30))  # success | blocked | failed | recovered
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Notification(Base, UUIDPKMixin):
    __tablename__ = "notifications"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SystemEvent(Base, UUIDPKMixin):
    __tablename__ = "system_events"

    merchant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
