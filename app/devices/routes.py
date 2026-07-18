from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse
from app.devices.schemas import DeviceConfirmPairingResponse, DevicePairingRequest, DeviceResponse
from app.devices.service import DeviceService
from app.users.models import User

router = APIRouter(prefix="/devices", tags=["devices"])


async def get_device_service() -> DeviceService:
    return DeviceService()


@router.post("/pair", response_model=ApiResponse[DeviceConfirmPairingResponse], status_code=status.HTTP_201_CREATED)
async def start_pairing(
    request: DevicePairingRequest,
    service: DeviceService = Depends(get_device_service)
):
    result = await service.start_pairing(request)
    return ApiResponse(data=result)


@router.post("/pair/{pairing_id}/confirm", response_model=ApiResponse[DeviceConfirmPairingResponse])
async def confirm_pairing(
    pairing_id: UUID,
    current_user: User = Depends(get_current_user),
    service: DeviceService = Depends(get_device_service)
):
    result = await service.confirm_pairing(pairing_id, current_user.id)
    return ApiResponse(data=result)


@router.get("", response_model=ApiResponse[list[DeviceResponse]])
async def list_devices(
    current_user: User = Depends(get_current_user),
    service: DeviceService = Depends(get_device_service)
):
    devices = await service.list_devices(current_user.id)
    return ApiResponse(data=devices)


@router.delete("/{device_id}", response_model=ApiResponse[dict])
async def revoke_device(
    device_id: UUID,
    current_user: User = Depends(get_current_user),
    service: DeviceService = Depends(get_device_service)
):
    await service.revoke_device(device_id, current_user.id)
    return ApiResponse(data={"revoked": True})
