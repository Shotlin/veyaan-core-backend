"""Unit tests for the emergency stop service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestEmergencyStopService:

    @pytest.mark.asyncio
    async def test_is_active_returns_true_from_valkey_cache(self):
        from app.emergency_stop.service import EmergencyStopService

        owner_id = uuid4()
        with patch("app.emergency_stop.service.valkey_client") as mock_valkey:
            mock_valkey.get = AsyncMock(return_value={"active": True})
            service = EmergencyStopService()
            result = await service.is_active(owner_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_active_returns_false_when_cache_says_inactive(self):
        from app.emergency_stop.service import EmergencyStopService

        owner_id = uuid4()
        with patch("app.emergency_stop.service.valkey_client") as mock_valkey:
            mock_valkey.get = AsyncMock(return_value={"active": False})
            service = EmergencyStopService()
            result = await service.is_active(owner_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_active_falls_back_to_db_when_cache_empty(self):
        from app.emergency_stop.service import EmergencyStopService

        owner_id = uuid4()

        mock_stop = MagicMock()
        mock_stop.active = True
        mock_stop.activated_at = datetime.now(timezone.utc)

        with patch("app.emergency_stop.service.valkey_client") as mock_valkey, \
             patch("app.emergency_stop.service.get_db_session") as mock_db:

            mock_valkey.get = AsyncMock(return_value=None)
            mock_valkey.set = AsyncMock()

            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_stop
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = EmergencyStopService()
            result = await service.is_active(owner_id)

        assert result is True
        mock_valkey.set.assert_called_once()  # should cache the result

    @pytest.mark.asyncio
    async def test_activate_persists_to_db_and_caches(self):
        from app.emergency_stop.service import EmergencyStopService

        owner_id = uuid4()
        actor_id = uuid4()

        mock_stop = MagicMock()
        mock_stop.active = True
        mock_stop.activated_at = datetime.now(timezone.utc)

        with patch("app.emergency_stop.service.valkey_client") as mock_valkey, \
             patch("app.emergency_stop.service.get_db_session") as mock_db, \
             patch("app.emergency_stop.service.AuditService") as mock_audit_class, \
             patch("app.emergency_stop.service.nats_client") as mock_nats:

            mock_audit = AsyncMock()
            mock_audit_class.return_value = mock_audit

            mock_valkey.set = AsyncMock()
            mock_nats.publish_js = AsyncMock()

            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = None  # no existing stop
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_session.add = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = EmergencyStopService()
            await service.activate(owner_id, "test reason", actor_id)

        mock_valkey.set.assert_called_once()  # cached after activation
        mock_nats.publish_js.assert_called_once()  # broadcast to devices

    @pytest.mark.asyncio
    async def test_release_clears_cache_and_broadcasts(self):
        from app.emergency_stop.service import EmergencyStopService

        owner_id = uuid4()
        released_by = uuid4()

        mock_stop = MagicMock()
        mock_stop.active = True

        with patch("app.emergency_stop.service.valkey_client") as mock_valkey, \
             patch("app.emergency_stop.service.get_db_session") as mock_db, \
             patch("app.emergency_stop.service.AuditService") as mock_audit_class, \
             patch("app.emergency_stop.service.nats_client") as mock_nats:

            mock_audit = AsyncMock()
            mock_audit_class.return_value = mock_audit

            mock_valkey.delete = AsyncMock()
            mock_nats.publish_js = AsyncMock()

            mock_session = AsyncMock()
            result_mock = MagicMock()
            result_mock.scalar_one_or_none.return_value = mock_stop
            mock_session.execute = AsyncMock(return_value=result_mock)
            mock_session.flush = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.refresh = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_db.return_value = mock_session

            service = EmergencyStopService()
            await service.release(owner_id, released_by)

        mock_valkey.delete.assert_called_once()  # cache cleared
        mock_nats.publish_js.assert_called_once()  # resume broadcast
