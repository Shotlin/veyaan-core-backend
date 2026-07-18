from uuid import UUID

from fastapi import APIRouter, Body, Depends, status

from app.api.dependencies import get_current_user_context
from app.api.responses import ApiResponse
from app.auth.user_context import UserContext
from app.devices.schemas import (
    DeviceConfirmPairingResponse,
    DevicePairingRequest,
    DevicePairingResponse,
    DeviceResponse,
)
from app.devices.service import DeviceService

router = APIRouter(prefix="/devices", tags=["devices"])


async def get_device_service() -> DeviceService:
    return DeviceService()


@router.post(
    "/pair", response_model=ApiResponse[DevicePairingResponse], status_code=status.HTTP_201_CREATED
)
async def start_pairing(
    request: DevicePairingRequest,
    service: DeviceService = Depends(get_device_service),
):
    result = await service.start_pairing(request)
    return ApiResponse(data=result)


@router.post("/pair/{pairing_id}/confirm", response_model=ApiResponse[DeviceConfirmPairingResponse])
async def confirm_pairing(
    pairing_id: UUID,
    pairing_code: str = Body(..., embed=True),
    current_user: UserContext = Depends(get_current_user_context),
    service: DeviceService = Depends(get_device_service),
):
    result = await service.confirm_pairing(pairing_id, current_user.id, pairing_code)
    return ApiResponse(data=result)


@router.get("", response_model=ApiResponse[list[DeviceResponse]])
async def list_devices(
    current_user: UserContext = Depends(get_current_user_context),
    service: DeviceService = Depends(get_device_service),
):
    devices = await service.list_devices(current_user.id)
    return ApiResponse(data=devices)


@router.get("/{device_id}", response_model=ApiResponse[DeviceResponse])
async def get_device(
    device_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: DeviceService = Depends(get_device_service),
):
    from app.api.errors import ApiError, ErrorCode
    from app.database.session import get_db_session
    from app.devices.repository import DeviceRepository

    async with get_db_session() as session:
        repo = DeviceRepository(session)
        device = await repo.get_device(device_id)
        if not device or str(device.owner_id) != str(current_user.id):
            raise ApiError(ErrorCode.DEVICE_NOT_FOUND, "Device not found", status_code=404)
        return ApiResponse(
            data=DeviceResponse(
                id=device.id,
                display_name=device.display_name,
                device_type=device.device_type,
                operating_system=device.operating_system,
                app_version=device.app_version,
                protocol_version=device.protocol_version,
                trust_status=device.trust_status.value
                if hasattr(device.trust_status, "value")
                else device.trust_status,
                last_seen_at=device.last_seen_at,
                created_at=device.created_at,
            )
        )


@router.delete("/{device_id}", response_model=ApiResponse[dict])
async def revoke_device(
    device_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: DeviceService = Depends(get_device_service),
):
    await service.revoke_device(device_id, current_user.id)
    return ApiResponse(data={"revoked": True})
