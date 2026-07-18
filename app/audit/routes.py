from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.audit.schemas import AuditLogResponse, PaginatedResponse
from app.audit.service import AuditService
from app.users.models import User

router = APIRouter(prefix="/audit", tags=["audit"])


async def get_audit_service() -> AuditService:
    return AuditService()


@router.get("/logs", response_model=ApiResponse[PaginatedResponse[AuditLogResponse]])
async def list_audit_logs(
    category: Optional[str] = Query(None, description="Filter by category"),
    action: Optional[str] = Query(None, description="Filter by action"),
    result: Optional[str] = Query(None, description="Filter by result"),
    device_id: Optional[UUID] = Query(None, description="Filter by device"),
    command_id: Optional[UUID] = Query(None, description="Filter by command"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: AuditService = Depends(AuditService),
):
    items, total, has_next, has_prev = await service.query_audit_logs(
        user_id=current_user.id,
        category=category,
        action=action,
        result=result,
        device_id=device_id,
        command_id=command_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ApiResponse(data={
        "items": [AuditLogResponse.model_validate(item) for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": has_next,
        "has_prev": has_prev,
    })
