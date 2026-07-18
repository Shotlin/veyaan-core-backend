from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.approvals.schemas import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
    ApprovalStatus,
    PaginatedResponse,
)
from app.approvals.service import ApprovalService
from app.users.models import User

router = APIRouter(prefix="/v1/approvals", tags=["approvals"])


async def get_approval_service() -> ApprovalService:
    return ApprovalService()


@router.post("", response_model=ApiResponse[ApprovalDecisionResponse], status_code=status.HTTP_201_CREATED)
async def create_approval(
    request: ApprovalCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    response, nonce = await service.create_approval(request, current_user.id)
    # Include nonce in response for client to use when deciding
    return ApiResponse(data={
        "approval_id": response.approval_id,
        "status": response.status,
        "decided_at": response.decided_at,
        "decision_nonce": nonce,  # Only returned once!
    })


@router.get("", response_model=ApiResponse[PaginatedResponse[ApprovalResponse]])
async def list_approvals(
    status: Optional[ApprovalStatus] = Query(None, description="Filter by status"),
    risk_level: Optional[str] = Query(None, description="Filter by risk level"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    approvals, total = await service.list_approvals(
        current_user.id,
        status=status.value if status else None,
        risk_level=risk_level,
        page=page,
        page_size=page_size,
    )
    items = [ApprovalResponse.model_validate(a) for a in approvals]
    has_next = (page * page_size) < total
    has_prev = page > 1
    return ApiResponse(data=PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=has_next,
        has_prev=has_prev,
    ))


@router.get("/{approval_id}", response_model=ApiResponse[ApprovalResponse])
async def get_approval(
    approval_id: UUID,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    approval = await service.get_approval(approval_id)
    if not approval or approval.owner_id != current_user.id:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.NOT_FOUND, "Approval not found", status_code=404)
    return ApiResponse(data=ApprovalResponse.model_validate(approval))


@router.post("/{approval_id}/approve", response_model=ApiResponse[ApprovalDecisionResponse])
async def approve(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    response = await service.decide_approval(
        approval_id=approval_id,
        owner_id=current_user.id,
        decision="approve",
        nonce=request.nonce,
        note=request.note,
    )
    return ApiResponse(data=response)


@router.post("/{approval_id}/reject", response_model=ApiResponse[ApprovalDecisionResponse])
async def reject(
    approval_id: UUID,
    request: ApprovalDecisionRequest,
    current_user: User = Depends(get_current_user),
    service: ApprovalService = Depends(get_approval_service),
):
    response = await service.decide_approval(
        approval_id=approval_id,
        owner_id=current_user.id,
        decision="reject",
        nonce=request.nonce,
        note=request.note,
    )
    return ApiResponse(data=response)
