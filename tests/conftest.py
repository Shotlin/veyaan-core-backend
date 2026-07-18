"""
Shared pytest fixtures for all test suites.

Integration tests require real service connections via env vars:
  DATABASE_URL, NATS_URL, VALKEY_URL (set by CI service containers)

Unit tests use mocks only and do not require running services.
"""

import asyncio
import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Event loop configuration (single event loop for entire test session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ---------------------------------------------------------------------------
# Integration test skip marker
# ---------------------------------------------------------------------------

def is_integration_env() -> bool:
    """True when real service connections are available."""
    return bool(
        os.getenv("DATABASE_URL")
        and os.getenv("NATS_URL")
        and os.getenv("VALKEY_URL")
    )


skip_if_no_services = pytest.mark.skipif(
    not is_integration_env(),
    reason="Integration tests require DATABASE_URL, NATS_URL, VALKEY_URL env vars",
)


# ---------------------------------------------------------------------------
# Common mock factories (unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_valkey():
    """A mock ValkeyClient that no-ops everything."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    client.exists = AsyncMock(return_value=False)
    client.get_hash = AsyncMock(return_value=None)
    client.set_hash = AsyncMock(return_value=True)
    client.delete_hash = AsyncMock(return_value=True)
    client.increment = AsyncMock(return_value=1)
    client.rate_limit_check = AsyncMock(return_value=(True, 1, 99))
    return client


@pytest.fixture
def mock_nats():
    """A mock NatsClient that no-ops publish/subscribe."""
    client = MagicMock()
    client.publish = AsyncMock()
    client.publish_js = AsyncMock()
    client.subscribe_durable = AsyncMock()
    client.is_connected = True
    return client


@pytest.fixture
def sample_user_id():
    return uuid4()


@pytest.fixture
def sample_device_id():
    return uuid4()


@pytest.fixture
def sample_owner_id():
    return uuid4()
