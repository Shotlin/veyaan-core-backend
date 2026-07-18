from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DevicePairingRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    device_type: str = Field(..., min_length=1, max_length=100)
    operating_system: str = Field(..., min_length=1, max_length=100)
    app_version: str = Field(..., min_length=1, max_length=50)
    device_public_identity: str = Field(..., min_length=1)
    protocol_version: str = Field(default="v1", max_length=20)


class DevicePairingResponse(BaseModel):
    pairing_request_id: UUID
    pairing_code: str
    expires_at: datetime


class DeviceConfirmPairingResponse(BaseModel):
    device_id: UUID
    credential: str
    pairing_status: str


class DeviceResponse(BaseModel):
    id: UUID
    display_name: str
    device_type: str
    operating_system: str
    app_version: str
    protocol_version: str
    trust_status: str
    last_seen_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RevokeDeviceRequest(BaseModel):
    pass  # Just the device_id in path
