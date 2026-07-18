from datetime import datetime
from typing import Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel


class HelloMessage(BaseModel):
    type: Literal["hello"] = "hello"
    device_id: UUID
    protocol_version: str
    app_version: str


class HeartbeatMessage(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    device_time: datetime
    state: str
    active_command_count: int
    app_version: str


class CommandAckMessage(BaseModel):
    type: Literal["acknowledge"] = "acknowledge"
    command_id: UUID
    accepted: bool
    rejection_reason: Optional[str] = None
    device_timestamp: datetime


class CommandProgressMessage(BaseModel):
    type: Literal["progress"] = "progress"
    command_id: UUID
    progress_percent: Optional[int] = None
    stage: Optional[str] = None
    status_message: Optional[str] = None


class CommandResultMessage(BaseModel):
    type: Literal["result"] = "result"
    command_id: UUID
    success: bool
    result_data: Optional[dict] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    started_at: datetime
    finished_at: datetime


class DeviceStatusUpdateMessage(BaseModel):
    type: Literal["status_update"] = "status_update"
    state: str
    metadata: Optional[dict] = None


# Server to device messages
class WelcomeMessage(BaseModel):
    type: Literal["welcome"] = "welcome"
    connection_id: UUID
    server_time: datetime
    heartbeat_interval: int
    protocol_version: str
    emergency_stop_active: bool


class CommandRequestMessage(BaseModel):
    type: Literal["command"] = "command"
    command_id: UUID
    command_type: str
    parameters: dict
    expires_at: datetime
    risk_metadata: dict
    trace_id: UUID


class CancelCommandMessage(BaseModel):
    type: Literal["cancel"] = "cancel"
    command_id: UUID
    reason: str


class EmergencyStopMessage(BaseModel):
    type: Literal["emergency_stop"] = "emergency_stop"
    reason: str


class ResumeAfterEmergencyStopMessage(BaseModel):
    type: Literal["resume"] = "resume"


class PingMessage(BaseModel):
    type: Literal["ping"] = "ping"


class ConfigRefreshMessage(BaseModel):
    type: Literal["config_refresh"] = "config_refresh"
    config: dict


# Union type for all client messages
ClientMessage = Union[
    HelloMessage,
    HeartbeatMessage,
    CommandAckMessage,
    CommandProgressMessage,
    CommandResultMessage,
    DeviceStatusUpdateMessage,
]

# Union type for all server messages
ServerMessage = Union[
    WelcomeMessage,
    CommandRequestMessage,
    CancelCommandMessage,
    EmergencyStopMessage,
    ResumeAfterEmergencyStopMessage,
    PingMessage,
    ConfigRefreshMessage,
]
