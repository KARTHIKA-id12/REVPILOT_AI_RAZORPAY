import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class Campaign(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "campaigns"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("revenue_opportunities.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    objective: Mapped[str] = mapped_column(String(100))
    segment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_segments.id"), nullable=True)
    product_ids_json: Mapped[list] = mapped_column(JSONB, default=list)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    budget_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    expected_revenue_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    actual_revenue_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(
        String(30), default="draft"
    )  # draft|pending_approval|approved|scheduled|running|paused|completed|failed|cancelled
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignTarget(Base, UUIDPKMixin):
    __tablename__ = "campaign_targets"

    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CampaignEvent(Base, UUIDPKMixin):
    __tablename__ = "campaign_events"

    campaign_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PolicyRule(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "policy_rules"
    __table_args__ = (UniqueConstraint("merchant_id", "code", name="uq_policy_rule_merchant_code"),)

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    code: Mapped[str] = mapped_column(String(100))  # MAX_DISCOUNT_PERCENT, MAX_CAMPAIGN_BUDGET, ...
    value_json: Mapped[dict] = mapped_column(JSONB, default=dict)


class AgentPermission(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "agent_permissions"
    __table_args__ = (UniqueConstraint("merchant_id", "action_code", name="uq_agent_permission_merchant_action"),)

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    action_code: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20))  # ALLOW | APPROVAL | DENY


class ApprovalRequest(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "approval_requests"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)
    action_code: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    risk_level: Mapped[str] = mapped_column(String(20))
    policy_result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|approved|rejected|edited
    requested_by_agent_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=True
    )
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
