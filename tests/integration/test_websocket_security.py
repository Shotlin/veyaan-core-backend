"""
Integration and security tests for WebSocket challenge-response authentication
and session management policies (Document 05).
"""

import asyncio
import base64
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from starlette.websockets import WebSocketDisconnect

from app.devices.models import Device, DeviceStatus
from app.websocket.gateway import connection_manager
from app.websocket.protocol.challenge import build_challenge_message


@pytest.fixture(autouse=True)
def clear_connections():
    connection_manager.active_connections.clear()
    yield
    connection_manager.active_connections.clear()


def _generate_device_keypair():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key_bytes = private_key.public_key().public_bytes_raw()
    public_key_b64 = base64.b64encode(public_key_bytes).decode("utf-8")
    return private_key, public_key_b64


class TestWebSocketSecurity:
    @pytest.mark.asyncio
    async def test_valid_challenge_handshake_succeeds(self):
        """Valid challenge-response signature successfully authenticates and registers connection."""
        device_id = uuid4()
        owner_id = uuid4()
        private_key, public_key_b64 = _generate_device_keypair()

        mock_device = MagicMock(spec=Device)
        mock_device.id = device_id
        mock_device.owner_id = owner_id
        mock_device.trust_status = DeviceStatus.TRUSTED
        mock_device.revoked_at = None
        mock_device.device_public_identity = public_key_b64

        mock_nonce = "abc123noncehex"
        sent_messages = []

        async def mock_send_json(data):
            sent_messages.append(data)

        receive_calls = 0

        async def mock_receive_bytes():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                challenge_msg = sent_messages[0]
                conn_id = challenge_msg["connection_id"]
                server_time = challenge_msg["server_time"]

                msg_bytes = build_challenge_message(
                    device_id=device_id,
                    connection_id=conn_id,
                    nonce=mock_nonce,
                    server_time_iso=server_time,
                    protocol_version="v1",
                    app_version="1.0.0",
                )
                sig = base64.b64encode(private_key.sign(msg_bytes)).decode("utf-8")

                payload = {
                    "type": "auth_response",
                    "device_id": str(device_id),
                    "signature": sig,
                    "protocol_version": "v1",
                    "app_version": "1.0.0",
                    "server_time": server_time,
                }
                return json.dumps(payload).encode("utf-8")
            else:
                assert device_id in connection_manager.active_connections
                raise WebSocketDisconnect(code=1000)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=mock_send_json)
        mock_ws.receive_bytes = AsyncMock(side_effect=mock_receive_bytes)

        with (
            patch("app.websocket.gateway.get_db_session") as mock_db,
            patch("app.websocket.gateway.generate_challenge", return_value=mock_nonce),
            patch(
                "app.websocket.gateway.verify_device_challenge_response", new_callable=AsyncMock
            ) as mock_verify,
            patch("app.websocket.gateway.valkey_client") as mock_valkey,
            patch("app.websocket.gateway.nats_client") as mock_nats,
            patch("app.websocket.gateway.EmergencyStopService") as mock_estop_service,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_service.return_value = mock_estop

            mock_verify.return_value = (True, "")
            mock_valkey.set_hash = AsyncMock()
            mock_valkey.get_hash = AsyncMock(return_value=None)
            mock_valkey.delete_hash = AsyncMock()

            # Mock NATS subscription
            mock_nats.js = AsyncMock()
            mock_sub = AsyncMock()
            mock_sub.fetch = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_nats.js.pull_subscribe = AsyncMock(return_value=mock_sub)

            from app.websocket.gateway import websocket_endpoint

            await websocket_endpoint(mock_ws, "v1", "1.0.0")

        assert len(sent_messages) == 2
        assert sent_messages[0]["type"] == "auth_challenge"
        assert sent_messages[1]["type"] == "welcome"

    @pytest.mark.asyncio
    async def test_invalid_signature_fails_handshake(self):
        """Invalid challenge-response signature fails authentication and closes connection."""
        device_id = uuid4()
        owner_id = uuid4()
        _, public_key_b64 = _generate_device_keypair()

        mock_device = MagicMock(spec=Device)
        mock_device.id = device_id
        mock_device.owner_id = owner_id
        mock_device.trust_status = DeviceStatus.TRUSTED
        mock_device.revoked_at = None
        mock_device.device_public_identity = public_key_b64

        mock_nonce = "abc123noncehex"
        sent_messages = []

        async def mock_send_json(data):
            sent_messages.append(data)

        receive_calls = 0

        async def mock_receive_bytes():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                payload = {
                    "type": "auth_response",
                    "device_id": str(device_id),
                    "signature": "badsigb64",
                    "protocol_version": "v1",
                    "app_version": "1.0.0",
                }
                return json.dumps(payload).encode("utf-8")
            else:
                raise WebSocketDisconnect(code=1000)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=mock_send_json)
        mock_ws.receive_bytes = AsyncMock(side_effect=mock_receive_bytes)

        with (
            patch("app.websocket.gateway.get_db_session") as mock_db,
            patch("app.websocket.gateway.generate_challenge", return_value=mock_nonce),
            patch("app.websocket.protocol.challenge.consume_challenge", return_value=True),
            patch("app.websocket.gateway.valkey_client") as mock_valkey,
            patch("app.websocket.gateway.EmergencyStopService") as mock_estop_service,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__.return_value = mock_session
            mock_valkey.set_hash = AsyncMock()
            mock_valkey.get_hash = AsyncMock(return_value=None)
            mock_valkey.delete_hash = AsyncMock()

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_service.return_value = mock_estop

            from app.websocket.gateway import websocket_endpoint

            await websocket_endpoint(mock_ws, "v1", "1.0.0")

        # Verify error message sent and connection closed
        assert len(sent_messages) == 2
        assert sent_messages[0]["type"] == "auth_challenge"
        assert sent_messages[1]["type"] == "error"
        assert sent_messages[1]["code"] == "AUTH_FAILED"
        mock_ws.close.assert_called_once_with(code=4001, reason="Auth failed")
        assert device_id not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_replayed_signature_or_consumed_nonce_fails(self):
        """Replaying a signature or consuming a nonce twice is rejected by nonce lookup deletion."""
        from app.websocket.protocol.challenge import verify_device_challenge_response

        device_id = uuid4()
        conn_id = uuid4()
        nonce = "somenonce"
        time_iso = datetime.now(timezone.utc).isoformat()
        private_key, public_key_b64 = _generate_device_keypair()

        msg = build_challenge_message(device_id, conn_id, nonce, time_iso, "v1", "1.0.0")
        sig = base64.b64encode(private_key.sign(msg)).decode("utf-8")

        with patch("app.websocket.protocol.challenge.valkey_client") as mock_valkey:
            mock_valkey.exists = AsyncMock(return_value=True)
            mock_valkey.delete = AsyncMock()

            ok, err = await verify_device_challenge_response(
                device_id, conn_id, nonce, time_iso, sig, public_key_b64, "v1", "1.0.0"
            )
            assert ok is True
            mock_valkey.delete.assert_called_once()

            mock_valkey.exists = AsyncMock(return_value=False)
            ok, err = await verify_device_challenge_response(
                device_id, conn_id, nonce, time_iso, sig, public_key_b64, "v1", "1.0.0"
            )
            assert ok is False
            assert "expired" in err.lower()

    @pytest.mark.asyncio
    async def test_expired_nonce_fails(self):
        """Nonces that are past TTL cannot be consumed and fail authentication."""
        from app.websocket.protocol.challenge import verify_device_challenge_response

        device_id = uuid4()
        conn_id = uuid4()
        nonce = "expirednonce"
        time_iso = datetime.now(timezone.utc).isoformat()
        _, public_key_b64 = _generate_device_keypair()

        with patch("app.websocket.protocol.challenge.valkey_client") as mock_valkey:
            mock_valkey.exists = AsyncMock(return_value=False)
            ok, err = await verify_device_challenge_response(
                device_id, conn_id, nonce, time_iso, "signature", public_key_b64, "v1", "1.0.0"
            )
            assert ok is False
            assert "expired" in err.lower()

    @pytest.mark.asyncio
    async def test_revoked_device_fails_handshake(self):
        """Handshake fails if the device is revoked or not trusted in the DB."""
        device_id = uuid4()
        owner_id = uuid4()
        _, public_key_b64 = _generate_device_keypair()

        mock_device = MagicMock(spec=Device)
        mock_device.id = device_id
        mock_device.owner_id = owner_id
        mock_device.trust_status = DeviceStatus.REVOKED
        mock_device.revoked_at = datetime.now(timezone.utc)
        mock_device.device_public_identity = public_key_b64

        mock_nonce = "abc123noncehex"
        sent_messages = []

        async def mock_send_json(data):
            sent_messages.append(data)

        receive_calls = 0

        async def mock_receive_bytes():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                payload = {
                    "type": "auth_response",
                    "device_id": str(device_id),
                    "signature": "sig",
                    "protocol_version": "v1",
                    "app_version": "1.0.0",
                }
                return json.dumps(payload).encode("utf-8")
            else:
                raise WebSocketDisconnect(code=1000)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=mock_send_json)
        mock_ws.receive_bytes = AsyncMock(side_effect=mock_receive_bytes)

        with (
            patch("app.websocket.gateway.get_db_session") as mock_db,
            patch("app.websocket.gateway.generate_challenge", return_value=mock_nonce),
            patch("app.websocket.gateway.EmergencyStopService") as mock_estop_service,
            patch("app.websocket.gateway.valkey_client") as mock_valkey,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__.return_value = mock_session
            mock_valkey.set_hash = AsyncMock()
            mock_valkey.get_hash = AsyncMock(return_value=None)
            mock_valkey.delete_hash = AsyncMock()

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_service.return_value = mock_estop

            from app.websocket.gateway import websocket_endpoint

            await websocket_endpoint(mock_ws, "v1", "1.0.0")

        # Verify closed with code 4001
        assert len(sent_messages) == 2
        assert sent_messages[1]["type"] == "error"
        assert sent_messages[1]["code"] == "AUTH_FAILED"
        mock_ws.close.assert_called_once_with(code=4001, reason="Device not authorized")
        assert device_id not in connection_manager.active_connections

    @pytest.mark.asyncio
    async def test_duplicate_connection_closes_old_connection_and_replaces(self):
        """New connection replacing duplicate registers in memory and closes the old socket."""
        device_id = uuid4()
        owner_id = uuid4()
        private_key, public_key_b64 = _generate_device_keypair()

        mock_device = MagicMock(spec=Device)
        mock_device.id = device_id
        mock_device.owner_id = owner_id
        mock_device.trust_status = DeviceStatus.TRUSTED
        mock_device.revoked_at = None
        mock_device.device_public_identity = public_key_b64

        old_socket = MagicMock()
        old_socket.close = AsyncMock()
        from app.websocket.gateway import DeviceConnection

        old_conn = DeviceConnection(device_id, owner_id, uuid4(), old_socket)
        connection_manager.active_connections[device_id] = old_conn

        mock_nonce = "newnoncehex"
        sent_messages = []

        async def mock_send_json(data):
            sent_messages.append(data)

        receive_calls = 0

        async def mock_receive_bytes():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                payload = {
                    "type": "auth_response",
                    "device_id": str(device_id),
                    "signature": "sig",
                    "protocol_version": "v1",
                    "app_version": "1.0.0",
                }
                return json.dumps(payload).encode("utf-8")
            else:
                # Verify the old connection was closed with duplicate replacing code
                old_socket.close.assert_called_once_with(
                    code=4000, reason="Replaced by new connection"
                )
                # New connection registered successfully
                assert device_id in connection_manager.active_connections
                assert connection_manager.active_connections[device_id] != old_conn
                raise WebSocketDisconnect(code=1000)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = AsyncMock(side_effect=mock_send_json)
        mock_ws.receive_bytes = AsyncMock(side_effect=mock_receive_bytes)

        with (
            patch("app.websocket.gateway.get_db_session") as mock_db,
            patch("app.websocket.gateway.generate_challenge", return_value=mock_nonce),
            patch(
                "app.websocket.gateway.verify_device_challenge_response", new_callable=AsyncMock
            ) as mock_verify,
            patch("app.websocket.gateway.valkey_client") as mock_valkey,
            patch("app.websocket.gateway.nats_client") as mock_nats,
            patch("app.websocket.gateway.EmergencyStopService") as mock_estop_service,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__.return_value = mock_session

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_service.return_value = mock_estop

            mock_verify.return_value = (True, "")
            mock_valkey.set_hash = AsyncMock()
            mock_valkey.get_hash = AsyncMock(return_value=None)
            mock_valkey.delete_hash = AsyncMock()

            # Mock NATS subscription
            mock_nats.js = AsyncMock()
            mock_sub = AsyncMock()
            mock_sub.fetch = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_nats.js.pull_subscribe = AsyncMock(return_value=mock_sub)

            from app.websocket.gateway import websocket_endpoint

            await websocket_endpoint(mock_ws, "v1", "1.0.0")

    @pytest.mark.asyncio
    async def test_old_disconnect_cannot_erase_new_presence(self):
        """Disconnecting old connection ID does not clear presence hash for new connection."""
        device_id = uuid4()
        old_conn_id = uuid4()
        new_conn_id = uuid4()

        with patch("app.websocket.gateway.valkey_client") as mock_valkey:
            mock_valkey.get_hash = AsyncMock(return_value={"connection_id": str(new_conn_id)})
            mock_valkey.delete_hash = AsyncMock()
            mock_valkey.delete = AsyncMock()

            await connection_manager.unregister(device_id, old_conn_id)

            mock_valkey.delete_hash.assert_not_called()
            mock_valkey.delete.assert_not_called()

            mock_valkey.get_hash.return_value = {"connection_id": str(new_conn_id)}
            await connection_manager.unregister(device_id, new_conn_id)

            mock_valkey.delete_hash.assert_called_once_with(f"device:connection:{device_id}")
            mock_valkey.delete.assert_called_once_with(f"device:presence:{device_id}")

    @pytest.mark.asyncio
    async def test_oversized_message_closes_connection(self):
        """WebSocket connection closes with code 1009 when message size exceeds limit."""
        device_id = uuid4()
        owner_id = uuid4()
        private_key, public_key_b64 = _generate_device_keypair()

        mock_device = MagicMock(spec=Device)
        mock_device.id = device_id
        mock_device.owner_id = owner_id
        mock_device.trust_status = DeviceStatus.TRUSTED
        mock_device.revoked_at = None
        mock_device.device_public_identity = public_key_b64

        mock_nonce = "abc123noncehex"
        sent_messages = []

        async def mock_send_json(data):
            sent_messages.append(data)

        receive_calls = 0

        async def mock_receive_bytes():
            nonlocal receive_calls
            receive_calls += 1
            if receive_calls == 1:
                payload = {
                    "type": "auth_response",
                    "device_id": str(device_id),
                    "signature": "sig",
                    "protocol_version": "v1",
                    "app_version": "1.0.0",
                }
                return json.dumps(payload).encode("utf-8")
            elif receive_calls == 2:
                # Oversized frame
                return b"x" * (1024 * 1024 + 100)
            else:
                raise WebSocketDisconnect(code=1000)

        mock_ws = MagicMock()
        mock_ws.accept = AsyncMock()
        mock_ws.close = AsyncMock()
        mock_ws.send_json = MagicMock(side_effect=mock_send_json)
        mock_ws.receive_bytes = AsyncMock(side_effect=mock_receive_bytes)

        with (
            patch("app.websocket.gateway.get_db_session") as mock_db,
            patch("app.websocket.gateway.generate_challenge", return_value=mock_nonce),
            patch(
                "app.websocket.gateway.verify_device_challenge_response", new_callable=AsyncMock
            ) as mock_verify,
            patch("app.websocket.gateway.valkey_client") as mock_valkey,
            patch("app.websocket.gateway.nats_client") as mock_nats,
            patch("app.websocket.gateway.EmergencyStopService") as mock_estop_service,
        ):
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_device
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_db.return_value.__aenter__.return_value = mock_session
            mock_valkey.set_hash = AsyncMock()
            mock_valkey.get_hash = AsyncMock(return_value=None)
            mock_valkey.delete_hash = AsyncMock()

            mock_estop = AsyncMock()
            mock_estop.is_active = AsyncMock(return_value=False)
            mock_estop_service.return_value = mock_estop

            mock_verify.return_value = (True, "")

            # Mock NATS
            mock_nats.js = AsyncMock()
            mock_sub = AsyncMock()
            mock_sub.fetch = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_nats.js.pull_subscribe = AsyncMock(return_value=mock_sub)

            from app.websocket.gateway import websocket_endpoint

            await websocket_endpoint(mock_ws, "v1", "1.0.0")

        # Verify close with code 1009 was called on mock_ws
        mock_ws.close.assert_called_with(
            code=1009, reason="Message exceeds maximum size of 1048576 bytes"
        )

    @pytest.mark.asyncio
    async def test_wrong_device_command_result_is_rejected(self):
        """Rejecting device command results where the target command belongs to another device."""
        from app.websocket.gateway import handle_device_message

        device_id = uuid4()
        owner_id = uuid4()

        payload_bytes = json.dumps(
            {
                "type": "result",
                "command_id": str(uuid4()),
                "success": True,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).encode("utf-8")

        with (
            patch(
                "app.websocket.gateway._command_belongs_to_device", return_value=False
            ) as mock_check,
            patch("app.websocket.gateway.nats_client") as mock_nats,
        ):
            mock_nats.publish = AsyncMock()

            await handle_device_message(device_id, owner_id, payload_bytes)

            mock_check.assert_called_once()
            mock_nats.publish.assert_not_called()
