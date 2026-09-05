import uuid

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class RevenueOpportunity(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "revenue_opportunities"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    type: Mapped[str] = mapped_column(String(50))
    # cross_sell | upsell | bundle | repeat_purchase | abandoned_cart | reactivation | retention | inventory_aware
    source_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    target_product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    segment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_segments.id"), nullable=True)
    reach_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    historical_affinity: Mapped[float] = mapped_column(Numeric(8, 4), default=0)  # lift
    estimated_conversion: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    estimated_revenue_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="low")  # low|medium|high|critical
    priority_score: Mapped[float] = mapped_column(Numeric(6, 2), default=0)  # 0-100
    evidence_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="open")  # open|actioned|dismissed|expired


class Recommendation(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "recommendations"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    context: Mapped[str] = mapped_column(String(100))  # dashboard | ai_buyer | campaign
    product_ids_json: Mapped[list] = mapped_column(JSONB, default=list)
    score: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    reason: Mapped[str] = mapped_column(String(500))
