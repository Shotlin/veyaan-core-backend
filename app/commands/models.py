import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database.connection import Base


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class CommandState(str, Enum):
    RECEIVED = "received"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    QUEUED = "queued"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    BLOCKED_BY_EMERGENCY_STOP = "blocked_by_emergency_stop"


class TaskState(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class Command(Base):
    __tablename__ = "commands"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id = Column(PG_UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    command_type = Column(String(100), nullable=False, index=True)
    parameters = Column(JSONB, nullable=False, default=dict)
    risk_level = Column(String(20), nullable=False, default=RiskLevel.LOW)
    idempotency_key = Column(String(255), nullable=False, index=True)
    request_fingerprint = Column(String(64), nullable=True)
    state = Column(String(50), nullable=False, default=CommandState.RECEIVED.value, index=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    delayed_execution_allowed = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result_data = Column(JSONB, nullable=True)
    result_summary = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    device = relationship("Device", back_populates="commands")
    task = relationship("Task", back_populates="command", uselist=False, cascade="all, delete-orphan")
    state_events = relationship("CommandStateEvent", back_populates="command", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("device_id", "idempotency_key", name="uq_device_idempotency"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id = Column(PG_UUID(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    state = Column(String(50), nullable=False, default=TaskState.PENDING.value, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    result_summary = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    command = relationship("Command", back_populates="task")


class CommandStateEvent(Base):
    __tablename__ = "command_state_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    command_id = Column(PG_UUID(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_state = Column(String(50), nullable=True)
    new_state = Column(String(50), nullable=False)
    event_source = Column(String(50), nullable=False)
    event_metadata = Column(JSONB, nullable=True)
    deduplication_key = Column(String(64), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    command = relationship("Command", back_populates="state_events")
