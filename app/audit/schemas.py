from datetime import datetime
from enum import Enum
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field


class AuditCategory(str, Enum):
    AUTH = "auth"
    DEVICE = "device"
    COMMAND = "command"
    APPROVAL = "approval"
    EMERGENCY_STOP = "emergency_stop"
    SECURITY = "security"
    SYSTEM = "system"


class AuditAction(str, Enum):
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


class AuditLogCreate(BaseModel):
    user_id: Optional[UUID] = None
    device_id: Optional[UUID] = None
    command_id: Optional[UUID] = None
    approval_id: Optional[UUID] = None
    category: AuditCategory
    action: AuditAction
    result: str
    metadata: Optional[dict] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    device_id: Optional[UUID]
    command_id: Optional[UUID]
    approval_id: Optional[UUID]
    category: AuditCategory
    action: AuditAction
    result: str
    metadata: Optional[str]
    request_id: Optional[str]
    trace_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ListAuditLogsFilters(BaseModel):
    category: Optional[AuditCategory] = None
    action: Optional[AuditAction] = None
    result: Optional[str] = None
    device_id: Optional[UUID] = None
    command_id: Optional[UUID] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
