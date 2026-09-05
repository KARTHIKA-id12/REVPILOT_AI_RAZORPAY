import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class ProductCategory(Base, UUIDPKMixin):
    __tablename__ = "product_categories"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=True)


class Product(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "products"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=True)
    stock_qty: Mapped[int] = mapped_column(Integer, default=0)
    stock_status: Mapped[str] = mapped_column(String(30), default="in_stock")  # in_stock | low_stock | out_of_stock
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    specifications_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags_json: Mapped[list] = mapped_column(JSONB, default=list)
    use_cases_json: Mapped[list] = mapped_column(JSONB, default=list)
    compatibility_json: Mapped[list] = mapped_column(JSONB, default=list)
    return_policy: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipping_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    discount_eligible: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="active")


class ProductRelation(Base, UUIDPKMixin):
    __tablename__ = "product_relations"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    related_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30))  # RELATED | FREQUENTLY_BOUGHT_WITH | COMPATIBLE


class InventoryEvent(Base, UUIDPKMixin):
    __tablename__ = "inventory_events"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
