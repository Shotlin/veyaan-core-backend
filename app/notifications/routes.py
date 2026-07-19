"""Notification API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.responses import ApiResponse
from app.auth.dependencies import get_current_user_context
from app.auth.user_context import UserContext
from app.database.session import get_db_session_context as get_db_session
from app.notifications.schemas import NotificationListResponse, NotificationResponse
from app.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=ApiResponse[NotificationListResponse])
async def list_notifications(
    user: UserContext = Depends(get_current_user_context),
    notification_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List notification records for the authenticated user."""
    async with get_db_session() as session:
        service = NotificationService(session)
        notifications, total = await service.list_for_user(
            user_id=user.id,
            notification_type=notification_type,
            page=page,
            page_size=page_size,
        )
        return ApiResponse(
            data=NotificationListResponse(
                items=[NotificationResponse.model_validate(n) for n in notifications],
                total=total,
                page=page,
                page_size=page_size,
                has_next=(page * page_size) < total,
                has_prev=page > 1,
            )
        )
