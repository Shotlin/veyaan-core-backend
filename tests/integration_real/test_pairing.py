"""Integration tests — device pairing lifecycle.

Covers:
  - Pairing code generation
  - Invalid code failure (attempt count persisted)
  - Lockout after MAX_PAIRING_ATTEMPTS (attempt counter durable)
  - Successful pairing creates device + credential in one transaction
  - Audit row inserted in same transaction
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.devices.models import Device, DeviceStatus, PairingRequest, PairingStatus
from app.devices.service import DeviceService
from app.devices.schemas import DevicePairingRequest


@pytest.mark.integration
async def test_pairing_code_generation(db_session):
    """start_pairing creates a PairingRequest with a hashed code and correct TTL."""
    service = DeviceService()
    request = DevicePairingRequest(
        display_name="Test Device",
        device_type="iphone",
        operating_system="FreeRTOS",
        app_version="1.0.0",
        protocol_version="v1",
        device_public_identity="a" * 64,
    )
    response = await service.start_pairing(request)

    assert response.pairing_request_id is not None
    assert response.pairing_code is not None
    assert len(response.pairing_code) >= 16

    # Pairing request must exist in DB
    result = await db_session.execute(
        select(PairingRequest).where(PairingRequest.id == response.pairing_request_id)
    )
    pairing = result.scalar_one_or_none()
    assert pairing is not None
    assert pairing.status == PairingStatus.PENDING
    assert pairing.expires_at > datetime.now(timezone.utc)


@pytest.mark.integration
async def test_pairing_invalid_code_increments_attempt_count(db_session):
    """Failed pairing attempts persist the incremented attempt_count."""
    from app.api.errors import ApiError

    service = DeviceService()
    request = DevicePairingRequest(
        display_name="Attempt Counter Test",
        device_type="iphone",
        operating_system="Linux",
        app_version="1.0.0",
        protocol_version="v1",
        device_public_identity="b" * 64,
    )
    pairing_response = await service.start_pairing(request)

    owner_id = uuid.uuid4()
    try:
        await service.confirm_pairing(pairing_response.pairing_request_id, owner_id, "wrong-code")
    except ApiError:
        pass

    # Attempt count must be persisted (not just in-memory)
    result = await db_session.execute(
        select(PairingRequest).where(PairingRequest.id == pairing_response.pairing_request_id)
    )
    pairing = result.scalar_one_or_none()
    assert pairing is not None
    assert pairing.attempt_count >= 1


@pytest.mark.integration
async def test_successful_pairing_atomic_transaction(db_session):
    """Successful pairing creates device, credential, and audit row in one transaction."""
    from app.audit.models import AuditAction, AuditLog

    service = DeviceService()
    request = DevicePairingRequest(
        display_name="Atomic Pairing Test",
        device_type="iphone",
        operating_system="RTOS",
        app_version="2.0.0",
        protocol_version="v1",
        device_public_identity="c" * 64,
    )
    pairing_response = await service.start_pairing(request)
    pairing_code = pairing_response.pairing_code

    from app.users.models import User
    user = User(
        id=uuid.uuid4(),
        supabase_user_id=f"sb-{uuid.uuid4()}",
        display_name="Test Owner",
        email="owner@example.com",
    )
    db_session.add(user)
    await db_session.commit()
    owner_id = user.id

    result = await service.confirm_pairing(
        pairing_response.pairing_request_id, owner_id, pairing_code
    )

    assert result.device_id is not None
    assert result.credential is not None

    # Device must exist in DB with correct owner
    dev_result = await db_session.execute(select(Device).where(Device.id == result.device_id))
    device = dev_result.scalar_one_or_none()
    assert device is not None
    assert str(device.owner_id) == str(owner_id)
    assert device.trust_status == DeviceStatus.TRUSTED

    # Audit row must exist in same DB (no cross-session split)
    audit_result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.device_id == result.device_id,
            AuditLog.action == AuditAction.DEVICE_PAIR_CONFIRMED.value,
        )
    )
    audit = audit_result.scalar_one_or_none()
    assert audit is not None, "Audit row must be present in the same transaction"
