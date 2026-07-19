"""Device service — pairing, listing, and revocation.

Transaction boundaries
----------------------
Every write path opens **one** ``get_db_session()`` context and passes the
session to dependent services (AuditService, OutboxRepository) so that the
device, credential, audit row and outbox event all commit or roll back
together.

Failed pairing attempts
-----------------------
attempt_count and status changes are persisted in their own explicit commit
*before* the ApiError is raised.  This ensures the security counter is
durable even when the client receives a 400/429 response.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.api.errors import ApiError, ErrorCode
from app.audit.models import AuditAction, AuditCategory
from app.audit.service import AuditService
from app.config import settings
from app.database.session import get_db_session_context as get_db_session
from app.devices.models import Device, DeviceCredential, DeviceStatus, PairingRequest, PairingStatus
from app.devices.repository import DeviceRepository
from app.devices.schemas import (
    DeviceConfirmPairingResponse,
    DevicePairingRequest,
    DevicePairingResponse,
    DeviceResponse,
)
from app.events import subjects
from app.events.outbox import OutboxRepository


class DeviceService:
    def __init__(self) -> None:
        pass

    async def start_pairing(self, request: DevicePairingRequest) -> DevicePairingResponse:
        async with get_db_session() as session:
            pairing_code = secrets.token_urlsafe(16)
            pairing_code_hash = hashlib.sha256(pairing_code.encode()).hexdigest()

            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=settings.PAIRING_CODE_TTL_MINUTES
            )

            pairing = PairingRequest(
                device_name=request.display_name,
                device_type=request.device_type,
                operating_system=request.operating_system,
                app_version=request.app_version,
                protocol_version=request.protocol_version or "v1",
                device_public_identity=request.device_public_identity,
                pairing_code_hash=pairing_code_hash,
                expires_at=expires_at,
                attempt_count=0,
            )

            session.add(pairing)
            await session.flush()
            await session.refresh(pairing)
            await session.commit()

            return DevicePairingResponse(
                pairing_request_id=pairing.id,
                pairing_code=pairing_code,
                expires_at=pairing.expires_at,
            )

    async def confirm_pairing(
        self, pairing_id: UUID, owner_id: UUID, pairing_code: str
    ) -> DeviceConfirmPairingResponse:
        """Confirm pairing atomically.

        Security counter (attempt_count / status) is persisted in an explicit
        commit before any ApiError is raised so failures are always durable.
        """
        error_to_raise: ApiError | None = None

        async with get_db_session() as session:
            result = await session.execute(
                select(PairingRequest).where(PairingRequest.id == pairing_id).with_for_update()
            )
            pairing = result.scalar_one_or_none()

            if not pairing:
                raise ApiError(
                    ErrorCode.PAIRING_INVALID, "Pairing request not found", status_code=404
                )

            if pairing.status != PairingStatus.PENDING:
                raise ApiError(
                    ErrorCode.PAIRING_INVALID,
                    f"Pairing is {pairing.status.value}",
                    status_code=400,
                )

            # ── Expiry check ────────────────────────────────────────────────
            if pairing.expires_at < datetime.now(timezone.utc):
                pairing.status = PairingStatus.EXPIRED
                await session.flush()
                await session.commit()
                raise ApiError(
                    ErrorCode.PAIRING_EXPIRED, "Pairing code has expired", status_code=400
                )

            # ── Attempt counter ─────────────────────────────────────────────
            max_attempts = settings.MAX_PAIRING_ATTEMPTS
            pairing.attempt_count = (pairing.attempt_count or 0) + 1

            if pairing.attempt_count > max_attempts:
                pairing.status = PairingStatus.REJECTED
                await session.flush()
                await session.commit()
                raise ApiError(
                    ErrorCode.PAIRING_INVALID,
                    "Too many failed pairing attempts",
                    status_code=429,
                )

            # ── Code verification ────────────────────────────────────────────
            code_hash = hashlib.sha256(pairing_code.encode()).hexdigest()
            if not hmac.compare_digest(code_hash, pairing.pairing_code_hash):
                # Persist the incremented attempt count before raising
                await session.flush()
                await session.commit()
                error_to_raise = ApiError(
                    ErrorCode.PAIRING_INVALID, "Invalid pairing code", status_code=400
                )
                # Re-open is not needed — raise immediately after persistence
                raise error_to_raise

            # ── Success path — device + credential + audit in ONE transaction ─
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

            session.add(device)
            await session.flush()

            credential_secret = secrets.token_urlsafe(32)
            credential_hash = hashlib.sha256(credential_secret.encode()).hexdigest()
            credential_expires = datetime.now(timezone.utc) + timedelta(
                days=settings.DEVICE_CREDENTIAL_TTL_DAYS
            )
            credential = DeviceCredential(
                device_id=device.id,
                credential_hash=credential_hash,
                expires_at=credential_expires,
            )
            session.add(credential)

            pairing.status = PairingStatus.CONFIRMED
            pairing.owner_id = owner_id
            pairing.confirmed_at = datetime.now(timezone.utc)

            await session.flush()

            # Audit row in the SAME session/transaction (P0-04 fix)
            audit = AuditService(session)
            await audit.create_audit_log(
                category=AuditCategory.DEVICE,
                action=AuditAction.DEVICE_PAIR_CONFIRMED,
                result="success",
                user_id=owner_id,
                device_id=device.id,
                metadata={"device_name": device.display_name},
            )

            # Single commit — device + credential + pairing + audit
            await session.commit()
            await session.refresh(device)

            return DeviceConfirmPairingResponse(
                device_id=device.id,
                credential=credential_secret,
                pairing_status="confirmed",
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
                    trust_status=d.trust_status.value
                    if hasattr(d.trust_status, "value")
                    else d.trust_status,
                    last_seen_at=d.last_seen_at,
                    created_at=d.created_at,
                )
                for d in devices
            ]

    async def revoke_device(self, device_id: UUID, owner_id: UUID) -> bool:
        """Revoke a device.

        All writes (revocation + audit + outbox event) commit in ONE
        transaction.  Gateway is notified via the outbox event (not by
        a direct NATS publish after commit).
        """
        async with get_db_session() as session:
            repo = DeviceRepository(session)
            result = await repo.revoke_device(device_id, owner_id)

            if not result:
                return False

            # Audit row in the same transaction (P0-04 fix)
            audit = AuditService(session)
            await audit.create_audit_log(
                category=AuditCategory.DEVICE,
                action=AuditAction.DEVICE_REVOKED,
                result="success",
                user_id=owner_id,
                device_id=device_id,
            )

            # Write device.revoked outbox event — gateway subscribes and closes
            # the WebSocket connection.  Outbox ensures delivery even if NATS
            # is temporarily unavailable (P0-13 fix).
            outbox = OutboxRepository(session)
            await outbox.add_event(
                event_type="device.revoked",
                aggregate_type="device",
                aggregate_id=str(device_id),
                subject=subjects.device_lifecycle(str(device_id)),
                payload={
                    "device_id": str(device_id),
                    "state": "revoked",
                    "owner_id": str(owner_id),
                },
            )

            # Single commit — revocation + audit + outbox event
            await session.commit()
            return True
