from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness():
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["status"] == "alive"


def test_readiness():
    response = client.get("/health/ready")
    # Just check it responds (will be 503 without DB)
    assert response.status_code in [200, 503]


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "VEYAAN API"


# Device tests (will fail without auth but test endpoint structure)
def test_devices_pair_endpoint_exists():
    response = client.post("/v1/devices/pair", json={
        "display_name": "Test MacBook",
        "device_type": "macbook",
        "operating_system": "macOS 14.0",
        "app_version": "1.0.0",
        "device_public_identity": "test-key-123"
    })
    # Should fail with 401 (no auth) or 500 (no DB), not 404
    assert response.status_code in [401, 500]


def test_devices_list_endpoint_exists():
    response = client.get("/v1/devices")
    assert response.status_code == 401


def test_devices_revoke_endpoint_exists():
    response = client.delete(f"/v1/devices/{uuid4()}")
    assert response.status_code == 401


def test_devices_confirm_pair_endpoint_exists():
    response = client.post(f"/v1/devices/pair/{uuid4()}/confirm")
    assert response.status_code == 401
