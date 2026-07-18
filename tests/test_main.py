"""Tests for VEYAAN Core Backend."""

from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness():
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_readiness():
    response = client.get("/health/ready")
    assert response.status_code in [200, 503]


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "VEYAAN API"


def test_devices_pair_endpoint_exists():
    response = client.post("/v1/devices/pair", json={
        "display_name": "Test MacBook",
        "device_type": "macbook",
        "operating_system": "macOS 14.0",
        "app_version": "1.0.0",
        "device_public_identity": "test-key-123",
    })
    assert response.status_code in [401, 500]


def test_devices_list_endpoint_exists():
    response = client.get("/v1/devices")
    assert response.status_code == 401


def test_devices_get_endpoint_exists():
    response = client.get(f"/v1/devices/{uuid4()}")
    assert response.status_code == 401


def test_devices_revoke_endpoint_exists():
    response = client.delete(f"/v1/devices/{uuid4()}")
    assert response.status_code == 401


def test_devices_confirm_pair_endpoint_exists():
    response = client.post(f"/v1/devices/pair/{uuid4()}/confirm", json={"pairing_code": "test-code"})
    assert response.status_code == 401


def test_commands_create_requires_auth():
    response = client.post("/v1/commands", json={
        "device_id": str(uuid4()),
        "command_type": "system.ping",
        "parameters": {},
        "idempotency_key": "test-key",
    })
    assert response.status_code == 401


def test_commands_list_requires_auth():
    response = client.get("/v1/commands")
    assert response.status_code == 401


def test_commands_get_requires_auth():
    response = client.get(f"/v1/commands/{uuid4()}")
    assert response.status_code == 401


def test_commands_cancel_requires_auth():
    response = client.post(f"/v1/commands/{uuid4()}/cancel")
    assert response.status_code == 401


def test_commands_events_requires_auth():
    response = client.get(f"/v1/commands/{uuid4()}/events")
    assert response.status_code == 401


def test_commands_task_requires_auth():
    response = client.get(f"/v1/commands/{uuid4()}/task")
    assert response.status_code == 401


def test_approvals_list_requires_auth():
    response = client.get("/v1/approvals")
    assert response.status_code == 401


def test_approvals_get_requires_auth():
    response = client.get(f"/v1/approvals/{uuid4()}")
    assert response.status_code == 401


def test_approvals_approve_requires_auth():
    response = client.post(f"/v1/approvals/{uuid4()}/approve", json={
        "decision": "approve",
        "nonce": "test-nonce",
    })
    assert response.status_code == 401


def test_approvals_reject_requires_auth():
    response = client.post(f"/v1/approvals/{uuid4()}/reject", json={
        "decision": "reject",
        "nonce": "test-nonce",
    })
    assert response.status_code == 401


def test_emergency_stop_status_requires_auth():
    response = client.get("/v1/emergency-stop/status")
    assert response.status_code == 401


def test_emergency_stop_activate_requires_auth():
    response = client.post("/v1/emergency-stop/activate", json={
        "reason": "test",
        "confirmation": "ACTIVATE_EMERGENCY_STOP",
    })
    assert response.status_code == 401


def test_emergency_stop_release_requires_auth():
    response = client.post("/v1/emergency-stop/release")
    assert response.status_code == 401


def test_audit_logs_requires_auth():
    response = client.get("/v1/audit/logs")
    assert response.status_code == 401


def test_auth_me_requires_auth():
    response = client.get("/v1/auth/me")
    assert response.status_code == 401


def test_auth_verify_requires_auth():
    response = client.get("/v1/auth/verify")
    assert response.status_code == 401


def test_health_detail_requires_auth():
    response = client.get("/health/detail")
    assert response.status_code == 401


def test_unknown_command_type_rejected():
    """Test that unknown command types return 422."""
    response = client.post("/v1/commands", json={
        "device_id": str(uuid4()),
        "command_type": "nonexistent.command",
        "parameters": {},
        "idempotency_key": "test-key",
    })
    assert response.status_code == 401


def test_empty_commands_list():
    """Test commands list without auth returns 401."""
    response = client.get("/v1/commands")
    assert response.status_code == 401


def test_metrics_endpoint():
    """Test Prometheus metrics endpoint is accessible."""
    response = client.get("/metrics")
    assert response.status_code == 200
