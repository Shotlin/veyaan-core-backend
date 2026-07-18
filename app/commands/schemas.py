from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.commands.models import CommandState, RiskLevel, TaskState


# Command parameter schemas
class PingParams(BaseModel):
    pass


class DeviceStatusParams(BaseModel):
    include_disk: bool = False
    include_memory: bool = False
    include_network: bool = False


class OpenTestAppParams(BaseModel):
    app_bundle_id: str = Field(..., min_length=1, max_length=255)
    args: list[str] = Field(default_factory=list)


class TakeScreenshotParams(BaseModel):
    display_id: Optional[int] = None
    format: str = Field(default="png", pattern="^(png|jpeg)$")
    quality: Optional[int] = Field(default=None, ge=1, le=100)


class EmergencyStopTestParams(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


# Command request/response
class CreateCommandRequest(BaseModel):
    device_id: UUID
    command_type: str
    parameters: dict = Field(default_factory=dict)
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    expires_at: Optional[datetime] = None
    delayed_execution_allowed: bool = False
    requires_approval: bool = False


class CreateCommandResponse(BaseModel):
    command_id: UUID
    task_id: UUID
    state: CommandState
    requires_approval: bool


class CommandResponse(BaseModel):
    id: UUID
    device_id: UUID
    command_type: str
    parameters: dict
    risk_level: RiskLevel
    idempotency_key: str
    state: CommandState
    requires_approval: bool
    delayed_execution_allowed: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class CommandListResponse(BaseModel):
    commands: list[CommandResponse]
    total: int
    page: int
    page_size: int


class TaskResponse(BaseModel):
    id: UUID
    command_id: UUID
    state: TaskState
    attempt_count: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True
