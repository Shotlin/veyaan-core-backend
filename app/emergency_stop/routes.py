
from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.emergency_stop.schemas import (
    EmergencyStopActivateRequest,
    EmergencyStopResponse,
    EmergencyStopStatusResponse,
)
from app.emergency_stop.service import EmergencyStopService
from app.users.models import User

router = APIRouter(prefix="/emergency-stop", tags=["emergency-stop"])


async def get_emergency_stop_service() -> EmergencyStopService:
    return EmergencyStopService()


@router.get("/status", response_model=ApiResponse[EmergencyStopStatusResponse])
async def get_status(
    current_user: User = Depends(get_current_user),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    status = await service.get_status(current_user.id)
    return ApiResponse(data=status)


@router.post("/activate", response_model=ApiResponse[EmergencyStopResponse], status_code=status.HTTP_201_CREATED)
async def activate(
    request: EmergencyStopActivateRequest,
    current_user: User = Depends(get_current_user),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    result = await service.activate(current_user.id, request)
    return ApiResponse(data=result)


@router.post("/release", response_model=ApiResponse[EmergencyStopResponse])
async def release(
    current_user: User = Depends(get_current_user),
    service: EmergencyStopService = Depends(get_emergency_stop_service),
):
    result = await service.release(current_user.id, current_user.id)
    if not result:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.NOT_FOUND, "Emergency stop not active", status_code=404)
    return ApiResponse(data=result)
