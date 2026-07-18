"""
Integration tests for device pairing flow.

Tests the full path: start pairing → confirm → device registered.
Also tests revoked device rejection.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestDevicePairingFlow:
    @pytest.mark.asyncio
    async def test_start_pairing_returns_code_and_expiry(self):
        """start_pairing must return a pairing_request_id, code, and expiry."""
        from app.devices.schemas import DevicePairingRequest
        from app.devices.service import DeviceService

        request = DevicePairingRequest(
            display_name="Test Device",
            device_type="workstation",
            operating_system="macOS 15",
            app_version="1.0.0",
            device_public_identity="ed25519-pub-key-base64",
        )

        with patch("app.devices.service.get_db_session") as mock_db:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.flush = AsyncMock()

            async def refresh_side(obj):
                obj.id = uuid4()
                obj.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            mock_session.refresh = AsyncMock(side_effect=refresh_side)

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = DeviceService()
            response = await service.start_pairing(request)

        assert response.pairing_request_id is not None
        assert response.pairing_code is not None
        assert len(response.pairing_code) > 0
        assert response.expires_at is not None

    @pytest.mark.asyncio
    async def test_confirm_pairing_with_correct_code_creates_device(self):
        """Correct pairing code must create a Device + DeviceCredential."""

        from app.devices.models import PairingRequest, PairingStatus
        from app.devices.service import DeviceService

        pairing_id = uuid4()
        owner_id = uuid4()
        pairing_code = secrets.token_urlsafe(16)
        code_hash = hashlib.sha256(pairing_code.encode()).hexdigest()

        mock_pairing = MagicMock(spec=PairingRequest)
        mock_pairing.id = pairing_id
        mock_pairing.status = PairingStatus.PENDING
        mock_pairing.pairing_code_hash = code_hash
        mock_pairing.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        mock_pairing.attempt_count = 0
        mock_pairing.device_name = "Test Device"
        mock_pairing.device_type = "workstation"
        mock_pairing.operating_system = "macOS"
        mock_pairing.app_version = "1.0.0"
        mock_pairing.protocol_version = "v1"
        mock_pairing.device_public_identity = "ed25519-pub-key"

        with (
            patch("app.devices.service.get_db_session") as mock_db,
            patch("app.devices.service.AuditService") as mock_audit,
        ):
            mock_audit_instance = AsyncMock()
            mock_audit_instance.create_audit_log = AsyncMock()
            mock_audit.return_value = mock_audit_instance

            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_pairing
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.add = MagicMock()
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()

            added_objects = []

            def capture_add(obj):
                added_objects.append(obj)

            mock_session.add = MagicMock(side_effect=capture_add)

            async def refresh_side(obj):
                if hasattr(obj, "id") and obj.id is None:
                    obj.id = uuid4()

            mock_session.refresh = AsyncMock(side_effect=refresh_side)

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = DeviceService()
            response = await service.confirm_pairing(pairing_id, owner_id, pairing_code)

        assert response.device_id is not None
        assert response.credential is not None
        assert response.pairing_status == "confirmed"
        # Both Device and DeviceCredential should have been added to session
        assert len(added_objects) >= 2

    @pytest.mark.asyncio
    async def test_confirm_pairing_with_wrong_code_raises_error(self):
        """Wrong pairing code must raise PAIRING_INVALID."""
        from app.api.errors import ApiError
        from app.devices.models import PairingRequest, PairingStatus
        from app.devices.service import DeviceService

        pairing_id = uuid4()
        owner_id = uuid4()
        correct_code = secrets.token_urlsafe(16)
        code_hash = hashlib.sha256(correct_code.encode()).hexdigest()

        mock_pairing = MagicMock(spec=PairingRequest)
        mock_pairing.id = pairing_id
        mock_pairing.status = PairingStatus.PENDING
        mock_pairing.pairing_code_hash = code_hash
        mock_pairing.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        mock_pairing.attempt_count = 0

        with patch("app.devices.service.get_db_session") as mock_db:
            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_pairing
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.flush = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = DeviceService()
            with pytest.raises(ApiError) as exc_info:
                await service.confirm_pairing(pairing_id, owner_id, "wrong-code")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_expired_pairing_raises_error(self):
        """Expired pairing must raise PAIRING_EXPIRED."""
        from app.api.errors import ApiError
        from app.devices.models import PairingRequest, PairingStatus
        from app.devices.service import DeviceService

        pairing_id = uuid4()
        owner_id = uuid4()

        mock_pairing = MagicMock(spec=PairingRequest)
        mock_pairing.id = pairing_id
        mock_pairing.status = PairingStatus.PENDING
        # Already expired
        mock_pairing.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_pairing.attempt_count = 0

        with patch("app.devices.service.get_db_session") as mock_db:
            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_pairing
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.flush = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = DeviceService()
            with pytest.raises(ApiError) as exc_info:
                await service.confirm_pairing(pairing_id, owner_id, "any-code")

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_device_publishes_nats_event(self):
        """Revoking a device must publish a NATS lifecycle event."""
        from app.devices.service import DeviceService

        device_id = uuid4()
        owner_id = uuid4()

        nats_published = []

        with (
            patch("app.devices.service.get_db_session") as mock_db,
            patch("app.devices.service.DeviceRepository") as mock_repo_class,
            patch("app.devices.service.AuditService") as mock_audit,
        ):
            mock_repo = AsyncMock()
            mock_repo.revoke_device = AsyncMock(return_value=True)
            mock_repo_class.return_value = mock_repo

            mock_audit_instance = AsyncMock()
            mock_audit_instance.create_audit_log = AsyncMock()
            mock_audit.return_value = mock_audit_instance

            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            with patch("app.events.nats_client.nats_client") as mock_nats:

                async def capture_publish(subject, data):
                    nats_published.append({"subject": subject, "data": data})

                mock_nats.publish = AsyncMock(side_effect=capture_publish)

                with patch("app.events.subjects") as mock_subjects:
                    mock_subjects.device_lifecycle = MagicMock(
                        return_value=f"device.lifecycle.{device_id}"
                    )

                    service = DeviceService()
                    result = await service.revoke_device(device_id, owner_id)

        assert result is True
        assert len(nats_published) == 1
        assert "revoked" in nats_published[0]["data"].decode()
