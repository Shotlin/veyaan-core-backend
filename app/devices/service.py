import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.api.errors import ApiError, ErrorCode
from app.database.session import get_db_session
from app.devices.models import Device, DeviceCredential, DeviceStatus, PairingRequest, PairingStatus
from app.devices.repository import DeviceRepository
from app.devices.schemas import (
    DeviceConfirmPairingResponse,
    DevicePairingRequest,
    DevicePairingResponse,
    DeviceResponse,
)


class DeviceService:
    def __init__(self):
        pass

    async def start_pairing(self, request: DevicePairingRequest) -> DevicePairingResponse:
        async with get_db_session() as session:

            # Generate secure pairing code
            pairing_code = secrets.token_urlsafe(16)
            pairing_code_hash = hashlib.sha256(pairing_code.encode()).hexdigest()

            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            pairing = PairingRequest(
                device_name=request.display_name,
                device_type=request.device_type,
                operating_system=request.operating_system,
                app_version=request.app_version,
                protocol_version="v1",
                device_public_identity=request.device_public_identity,
                pairing_code_hash=pairing_code_hash,
                expires_at=expires_at
            )

            session.add(pairing)
            await session.flush()
            await session.refresh(pairing)

            return DevicePairingResponse(
                pairing_request_id=pairing.id,
                pairing_code=pairing_code,
                expires_at=pairing.expires_at
            )

    async def confirm_pairing(self, pairing_id: UUID, owner_id: UUID) -> DeviceConfirmPairingResponse:
        async with get_db_session() as session:

            result = await session.execute(
                select(PairingRequest).where(PairingRequest.id == pairing_id)
            )
            pairing = result.scalar_one_or_none()

            if not pairing:
                raise ApiError(ErrorCode.PAIRING_INVALID, "Pairing request not found")

            if pairing.status != PairingStatus.PENDING:
                raise ApiError(ErrorCode.PAIRING_INVALID, f"Pairing is {pairing.status.value}")

            if pairing.expires_at < datetime.now(timezone.utc):
                pairing.status = PairingStatus.EXPIRED
                await session.flush()
                raise ApiError(ErrorCode.PAIRING_EXPIRED, "Pairing code has expired")

            # Generate device credential
            credential_secret = secrets.token_urlsafe(32)
            credential_hash = hashlib.sha256(credential_secret.encode()).hexdigest()

            # Create device
            device = Device(
                owner_id=owner_id,
                display_name=pairing.device_name,
                device_type=pairing.device_type,
                operating_system=pairing.operating_system,
                app_version=pairing.app_version,
                protocol_version=pairing.protocol_version,
                device_public_identity=pairing.device_public_identity,
                trust_status=DeviceStatus.TRUSTED
            )

            session.add(device)
            await session.flush()

            # Create credential
            expires_at = datetime.now(timezone.utc) + timedelta(days=365)
            credential = DeviceCredential(
                device_id=device.id,
                credential_hash=credential_hash,
                expires_at=expires_at
            )

            session.add(credential)

            # Update pairing
            pairing.status = PairingStatus.CONFIRMED
            pairing.owner_id = owner_id
            pairing.confirmed_at = datetime.now(timezone.utc)

            await session.flush()
            await session.refresh(device)

            return DeviceConfirmPairingResponse(
                device_id=device.id,
                credential=credential_secret,
                pairing_status="confirmed"
            )

    async def list_devices(self, owner_id: UUID) -> list[DeviceResponse]:
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            devices = await repo.list_devices_by_owner(owner_id)

            return [
                DeviceResponse(
                    id=d.id,
                    display_name=d.display_name,
                    device_type=d.device_type,
                    operating_system=d.operating_system,
                    app_version=d.app_version,
                    protocol_version=d.protocol_version,
                    trust_status=d.trust_status,
                    last_seen_at=d.last_seen_at,
                    created_at=d.created_at
                )
                for d in devices
            ]

    async def revoke_device(self, device_id: UUID, owner_id: UUID) -> bool:
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            result = await repo.revoke_device(device_id, owner_id)
            if not result:
                raise ApiError(ErrorCode.DEVICE_NOT_FOUND, "Device not found")
            return True
