"""Integration test conftest — uses real PostgreSQL, NATS and Valkey.

Environment variables required:
  DATABASE_URL=postgresql+asyncpg://veyaan:dev_password@localhost:5432/veyaan_dev
  NATS_URL=nats://localhost:4222
  VALKEY_URL=redis://localhost:6379

Run with: pytest tests/integration_real

All tests use real infrastructure — no mocks of production behaviour.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator

import pytest
# Ensure all SQLAlchemy models are registered
import app.database.models  # noqa: F401

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.database.connection import engine, async_session_maker as AsyncSessionLocal


@pytest_asyncio.fixture(scope="function")
async def db_session(setup_infrastructure) -> AsyncGenerator[AsyncSession, None]:
    """Provide a test session."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_infrastructure():
    """Connect Valkey and NATS fresh for each test function."""
    from app.cache import valkey_client
    from app.events.nats_client import nats_client

    # Force reset internal clients to prevent any old event loop references
    valkey_client.client = None
    nats_client.nc = None
    nats_client.js = None

    await valkey_client.connect()
    await nats_client.connect()

    yield

    await nats_client.disconnect()
    await valkey_client.disconnect()

    valkey_client.client = None
    nats_client.nc = None
    nats_client.js = None

    from app.database.connection import cleanup_all_engines
    await cleanup_all_engines()





def unique_id() -> str:
    return str(uuid.uuid4())
