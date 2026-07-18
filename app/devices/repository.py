from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.devices.models import Device, DeviceCredential, DeviceStatus, PairingRequest, PairingStatus


class DeviceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_pairing_request(
        self,
        device_name: str,
        device_type: str,
        operating_system: str,
        app_version: str,
        device_public_identity: str,
        protocol_version: str = "v1",
    ) -> PairingRequest:
        pairing_code, code_hash = Device.generate_pairing_code()

        expires_at = datetime.now(timezone.utc).replace(
            minute=datetime.now(timezone.utc).minute + 10
        )

        pairing = PairingRequest(
            device_name=device_name,
            device_type=device_type,
            operating_system=operating_system,
            app_version=app_version,
            protocol_version=protocol_version,
            device_public_identity=device_public_identity,
            pairing_code_hash=code_hash,
            expires_at=expires_at,
        )

        # Store raw pairing code temporarily for response
        pairing._raw_pairing_code = pairing_code

        self.session.add(pairing)
        await self.session.flush()
        await self.session.refresh(pairing)
        return pairing

    async def get_pairing_request(self, pairing_id: UUID) -> Optional[PairingRequest]:
        result = await self.session.execute(
            select(PairingRequest).where(PairingRequest.id == pairing_id)
        )
        return result.scalar_one_or_none()

    async def confirm_pairing(
        self, pairing_id: UUID, owner_id: UUID
    ) -> tuple[Optional[Device], Optional[str]]:
        pairing = await self.get_pairing_request(pairing_id)

        if not pairing:
            return None, None

        if pairing.status != PairingStatus.PENDING:
            return None, None

        if pairing.expires_at < datetime.now(timezone.utc):
            pairing.status = PairingStatus.EXPIRED
            await self.session.flush()
            return None, None

        # Generate device credential
        credential, credential_hash = Device.generate_credential()

        # Create device
        device = Device(
            owner_id=owner_id,
            display_name=pairing.device_name,
            device_type=pairing.device_type,
            operating_system=pairing.operating_system,
            app_version=pairing.app_version,
            protocol_version=pairing.protocol_version,
            device_public_identity=pairing.device_public_identity,
            trust_status=DeviceStatus.TRUSTED,
        )

        self.session.add(device)
        await self.session.flush()

        # Create credential
        device_credential = DeviceCredential(
            device_id=device.id,
            credential_hash=credential_hash,
            expires_at=datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1),
        )

        self.session.add(device_credential)

        # Update pairing
        pairing.status = PairingStatus.CONFIRMED
        pairing.owner_id = owner_id
        pairing.confirmed_at = datetime.now(timezone.utc)

        await self.session.flush()
        await self.session.refresh(device)

        return device, credential

    async def list_devices_by_owner(self, owner_id: UUID) -> list[Device]:
        result = await self.session.execute(
            select(Device).where(Device.owner_id == owner_id).order_by(Device.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_device(self, device_id: UUID) -> Optional[Device]:
        result = await self.session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    async def revoke_device(self, device_id: UUID, owner_id: UUID) -> bool:
        result = await self.session.execute(
            select(Device).where(and_(Device.id == device_id, Device.owner_id == owner_id))
        )
        device = result.scalar_one_or_none()

        if not device:
            return False

        device.trust_status = DeviceStatus.REVOKED
        device.revoked_at = datetime.now(timezone.utc)

        # Revoke all credentials
        await self.session.execute(
            update(DeviceCredential)
            .where(DeviceCredential.device_id == device_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )

        await self.session.flush()
        return True

    async def get_active_credential(self, device_id: UUID) -> Optional[DeviceCredential]:
        result = await self.session.execute(
            select(DeviceCredential)
            .where(
                and_(
                    DeviceCredential.device_id == device_id,
                    DeviceCredential.revoked_at.is_(None),
                    DeviceCredential.expires_at > datetime.now(timezone.utc),
                )
            )
            .order_by(DeviceCredential.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def update_last_seen(self, device_id: UUID) -> bool:
        result = await self.session.execute(
            update(Device)
            .where(Device.id == device_id)
            .values(last_seen_at=datetime.now(timezone.utc))
        )
        return result.rowcount > 0
