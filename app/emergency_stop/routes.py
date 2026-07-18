from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user_context
from app.api.responses import ApiResponse
from app.auth.user_context import UserContext
from app.emergency_stop.schemas import (
    EmergencyStopActivateRequest,
    EmergencyStopResponse,
    EmergencyStopStatusResponse,
)
from app.emergency_stop.service import EmergencyStopService

router = APIRouter(prefix="/emergency-stop", tags=["emergency-stop"])


async def get_emergency_stop_service() -> EmergencyStopService:
    return EmergencyStopService()


@router.get("/status", response_model=ApiResponse[EmergencyStopStatusResponse])
async def get_status(
    current_user: UserContext = Depends(get_current_user_context),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    result = await service.get_status(current_user.id)
    if result:
        return ApiResponse(data=EmergencyStopStatusResponse(
            active=result.active,
            reason=result.reason,
            activated_at=result.activated_at,
        ))
    return ApiResponse(data=EmergencyStopStatusResponse(active=False))


@router.post("/activate", response_model=ApiResponse[EmergencyStopResponse], status_code=status.HTTP_201_CREATED)
async def activate(
    request: EmergencyStopActivateRequest,
    current_user: UserContext = Depends(get_current_user_context),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    from app.api.errors import ApiError, ErrorCode

    if request.confirmation != "ACTIVATE_EMERGENCY_STOP":
        raise ApiError(ErrorCode.INVALID_CONFIRMATION, "Confirmation phrase must be ACTIVATE_EMERGENCY_STOP", status_code=400)

    result = await service.activate(current_user.id, request.reason or "No reason provided", current_user.id)
    return ApiResponse(data=EmergencyStopResponse.model_validate(result))


@router.post("/release", response_model=ApiResponse[EmergencyStopResponse])
async def release(
    current_user: UserContext = Depends(get_current_user_context),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    from app.api.errors import ApiError, ErrorCode

    result = await service.release(current_user.id, current_user.id)
    if not result:
        raise ApiError(ErrorCode.EMERGENCY_STOP_NOT_ACTIVE, "Emergency stop not active", status_code=404)
    return ApiResponse(data=EmergencyStopResponse.model_validate(result))
