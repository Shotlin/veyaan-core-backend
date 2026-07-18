import enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database.connection import Base


class AuditCategory(str, enum.Enum):
    AUTH = "auth"
    DEVICE = "device"
    COMMAND = "command"
    APPROVAL = "approval"
    EMERGENCY_STOP = "emergency_stop"
    SECURITY = "security"
    SYSTEM = "system"


class AuditAction(str, enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    DEVICE_PAIR_STARTED = "device_pair_started"
    DEVICE_PAIR_CONFIRMED = "device_pair_confirmed"
    DEVICE_REVOKED = "device_revoked"
    DEVICE_CONNECTED = "device_connected"
    DEVICE_DISCONNECTED = "device_disconnected"
    COMMAND_CREATED = "command_created"
    COMMAND_DELIVERED = "command_delivered"
    COMMAND_ACKNOWLEDGED = "command_acknowledged"
    COMMAND_STARTED = "command_started"
    COMMAND_SUCCEEDED = "command_succeeded"
    COMMAND_FAILED = "command_failed"
    COMMAND_CANCELLED = "command_cancelled"
    COMMAND_EXPIRED = "command_expired"
    COMMAND_BLOCKED = "command_blocked"
    APPROVAL_CREATED = "approval_created"
    APPROVAL_APPROVED = "approval_approved"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    EMERGENCY_STOP_ACTIVATED = "emergency_stop_activated"
    EMERGENCY_STOP_RELEASED = "emergency_stop_released"
    INVALID_TOKEN = "invalid_token"
    INVALID_CREDENTIAL = "invalid_credential"
    REPLAY_ATTEMPT = "replay_attempt"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    CONFIG_CHANGED = "config_changed"
    BACKUP_STARTED = "backup_started"
    BACKUP_COMPLETED = "backup_completed"
    RESTORE_STARTED = "restore_started"
    RESTORE_COMPLETED = "restore_completed"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    device_id = Column(PG_UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    command_id = Column(PG_UUID(as_uuid=True), ForeignKey("commands.id", ondelete="SET NULL"), nullable=True, index=True)
    approval_id = Column(PG_UUID(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL"), nullable=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    result = Column(String(50), nullable=False)
    event_metadata = Column(JSONB, nullable=True)
    request_id = Column(String(64), nullable=True, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    user = relationship("User")
    device = relationship("Device")
    command = relationship("Command")
    approval = relationship("Approval")
