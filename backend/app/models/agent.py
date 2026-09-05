import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.db.session import Base


class AgentSession(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "agent_sessions"

    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(30))  # merchant_console | ai_buyer
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | ended
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base, UUIDPKMixin):
    __tablename__ = "agent_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant | system
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentToolCall(Base, UUIDPKMixin):
    __tablename__ = "agent_tool_calls"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(100))
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))  # ok | error
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentAction(Base, UUIDPKMixin):
    __tablename__ = "agent_actions"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"), index=True)
    action_code: Mapped[str] = mapped_column(String(100))
    input_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    policy_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    permission_result: Mapped[str] = mapped_column(String(20))  # allow | approval | deny
    risk_level: Mapped[str] = mapped_column(String(20))
    approval_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("approval_requests.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # proposed | blocked | pending_approval | executed | failed
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
