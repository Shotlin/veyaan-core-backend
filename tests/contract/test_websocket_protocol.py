"""
Contract tests — WebSocket protocol version enforcement.

Verifies that unsupported protocol versions are rejected with a clear
error message, and that supported versions are accepted.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest


class TestWebSocketProtocolContract:
    @pytest.mark.asyncio
    async def test_unsupported_protocol_version_rejected(self):
        """
        Devices sending an unsupported protocol version in the auth response
        must be rejected with a clear structured error.
        """
        from app.websocket.gateway import _validate_protocol_version

        # Version "v99" is not in WS_SUPPORTED_PROTOCOLS (only ["v1"])
        with patch("app.websocket.gateway.settings") as mock_settings:
            mock_settings.WS_SUPPORTED_PROTOCOLS = ["v1"]
            result = _validate_protocol_version("v99")

        assert result is False, "Unsupported protocol version should be rejected"

    @pytest.mark.asyncio
    async def test_supported_protocol_version_accepted(self):
        """Protocol version 'v1' must be accepted."""
        from app.websocket.gateway import _validate_protocol_version

        with patch("app.websocket.gateway.settings") as mock_settings:
            mock_settings.WS_SUPPORTED_PROTOCOLS = ["v1"]
            result = _validate_protocol_version("v1")

        assert result is True

    @pytest.mark.asyncio
    async def test_empty_protocol_version_rejected(self):
        """Empty or None protocol version must be rejected."""
        from app.websocket.gateway import _validate_protocol_version

        with patch("app.websocket.gateway.settings") as mock_settings:
            mock_settings.WS_SUPPORTED_PROTOCOLS = ["v1"]
            assert _validate_protocol_version("") is False
            assert _validate_protocol_version(None) is False


class TestOpenApiSchemaContract:
    """Verify that the OpenAPI schema contains required endpoint paths."""

    @pytest.mark.asyncio
    async def test_openapi_schema_has_required_paths(self):
        """
        The FastAPI OpenAPI schema must contain all required API endpoints
        as defined in the spec.
        """
        from app.main import app

        client_paths = app.openapi()["paths"].keys()

        required_paths = [
            "/health/live",
            "/health/ready",
            "/v1/devices/pair",
            "/v1/devices/pair/{pairing_id}/confirm",
            "/v1/commands",
            "/v1/approvals",
            "/v1/emergency-stop/activate",
            "/v1/emergency-stop/release",
            "/v1/emergency-stop/status",
        ]

        for path in required_paths:
            assert path in client_paths, f"Required API path missing from OpenAPI schema: {path}"

    @pytest.mark.asyncio
    async def test_openapi_schema_has_security_schemes(self):
        """OpenAPI schema must declare a bearer token security scheme."""
        from app.main import app

        schema = app.openapi()
        components = schema.get("components", {})
        security_schemes = components.get("securitySchemes", {})

        # Must have at least one bearer-based scheme
        has_bearer = any(
            scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
            for scheme in security_schemes.values()
        )
        assert has_bearer, "OpenAPI schema must declare a Bearer token security scheme"

    @pytest.mark.asyncio
    async def test_command_create_schema_requires_idempotency_key(self):
        """CreateCommandRequest schema must require idempotency_key."""
        import pydantic

        from app.commands.schemas import CreateCommandRequest

        # Missing idempotency_key must fail validation
        with pytest.raises((ValueError, pydantic.ValidationError)):
            CreateCommandRequest(
                device_id=uuid4(),
                command_type="system.ping",
                parameters={},
                # idempotency_key intentionally omitted
            )

    @pytest.mark.asyncio
    async def test_approval_decision_enum_validated(self):
        """ApprovalDecisionRequest must only accept 'approve' or 'reject'."""
        import pydantic

        from app.approvals.schemas import ApprovalDecisionRequest

        # Valid decisions
        req = ApprovalDecisionRequest(decision="approve", nonce="abc123")
        assert req.decision.value == "approve"

        req2 = ApprovalDecisionRequest(decision="reject", nonce="abc123")
        assert req2.decision.value == "reject"

        # Invalid decision
        with pytest.raises((ValueError, pydantic.ValidationError)):
            ApprovalDecisionRequest(decision="maybe", nonce="abc123")
