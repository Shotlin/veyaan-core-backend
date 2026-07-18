from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmergencyStopStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class EmergencyStopActivateRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=1000)
    confirmation: str = Field(..., min_length=1)  # Must match "ACTIVATE_EMERGENCY_STOP"


class EmergencyStopReleaseRequest(BaseModel):
    confirmation: str = Field(..., min_length=1)  # Must match "RELEASE_EMERGENCY_STOP"
    reason: Optional[str] = Field(default=None, max_length=1000)


class EmergencyStopResponse(BaseModel):
    id: UUID
    owner_id: UUID
    active: bool
    reason: Optional[str] = None
    activated_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    activated_by: Optional[UUID] = None
    released_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmergencyStopStatusResponse(BaseModel):
    active: bool
    reason: Optional[str] = None
    activated_at: Optional[datetime] = None
