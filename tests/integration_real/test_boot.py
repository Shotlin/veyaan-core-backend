"""Integration tests — clean boot and migration validation.

Gate: `alembic upgrade head && alembic check` must both succeed on a clean DB.
"""

import subprocess
import sys

import httpx
import pytest


@pytest.mark.integration
async def test_health_live(unused_tcp_port_factory=None):
    """API /health/live must return 200 with status=alive."""
    api_url = "http://localhost:8000"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{api_url}/health/live")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    body = response.json()
    assert body.get("status") == "alive" or body.get("alive") is True, (
        f"Unexpected body: {body}"
    )


@pytest.mark.integration
async def test_alembic_check():
    """alembic check must exit 0 (no pending migrations)."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic check failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@pytest.mark.integration
async def test_openapi_schema_reachable():
    """OpenAPI JSON must be available in development mode."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get("http://localhost:8000/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema


@pytest.mark.integration
async def test_metrics_endpoint():
    """Prometheus /metrics endpoint must be reachable."""
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get("http://localhost:8000/metrics/")
    assert response.status_code == 200
    assert "process_virtual_memory_bytes" in response.text or "python_gc_objects" in response.text
