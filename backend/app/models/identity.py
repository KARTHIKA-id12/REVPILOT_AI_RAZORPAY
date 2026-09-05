import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Merchant(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "merchants"

    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")


class MerchantSettings(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "merchant_settings"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_provider: Mapped[str] = mapped_column(String(20), default="mock")
    emergency_stop_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class MerchantCredential(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "merchant_credentials"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    key_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Base, UUIDPKMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True)  # OWNER, ADMIN, ANALYST, VIEWER


class Permission(Base, UUIDPKMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Team(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "teams"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))


class UserMerchantRole(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "user_merchant_roles"
    __table_args__ = (UniqueConstraint("user_id", "merchant_id", name="uq_user_merchant"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"))

    user: Mapped["User"] = relationship()
    merchant: Mapped["Merchant"] = relationship()
    role: Mapped["Role"] = relationship()
