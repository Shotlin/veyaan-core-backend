from datetime import datetime
from enum import Enum
from typing import Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class ApprovalCreateRequest(BaseModel):
    command_id: UUID
    risk_level: RiskLevel
    action_title: str = Field(..., min_length=1, max_length=255)
    action_description: str = Field(..., min_length=1, max_length=2000)
    expires_in_minutes: int = Field(default=30, ge=1, le=1440)


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    nonce: str = Field(..., min_length=1, description="Decision nonce from approval creation")
    note: Optional[str] = None


class ApprovalDecisionResponse(BaseModel):
    approval_id: UUID
    status: ApprovalStatus
    decided_at: Optional[datetime] = None


class ApprovalResponse(BaseModel):
    id: UUID
    command_id: UUID
    owner_id: UUID
    risk_level: str
    action_title: str
    action_description: str
    status: ApprovalStatus
    expires_at: datetime
    decided_at: Optional[datetime] = None
    decision_note: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool


class ListApprovalsFilters(BaseModel):
    status: Optional[str] = None
    risk_level: Optional[str] = None
