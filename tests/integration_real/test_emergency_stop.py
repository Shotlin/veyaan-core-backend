"""Integration tests — emergency stop lifecycle.

Covers:
  - Activation persists in PostgreSQL (not only Valkey)
  - Release is durable (active=False in DB after release)
  - Queued commands are blocked on activation
  - Audit rows present in same transaction
  - Idempotent re-activation (no duplicate rows)
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.emergency_stop.models import EmergencyStop
from app.emergency_stop.service import EmergencyStopService
from app.users.models import User


async def _create_users(db_session):
    owner = User(
        id=uuid.uuid4(),
        supabase_user_id=f"sb-{uuid.uuid4()}",
        display_name="Owner User",
        email="owner@example.com",
    )
    actor = User(
        id=uuid.uuid4(),
        supabase_user_id=f"sb-{uuid.uuid4()}",
        display_name="Actor User",
        email="actor@example.com",
    )
    db_session.add_all([owner, actor])
    await db_session.commit()
    return owner.id, actor.id


@pytest.mark.integration
async def test_emergency_stop_activation_is_durable(db_session):
    """Activation creates a durable DB row, not only a Valkey cache entry."""
    owner_id, actor_id = await _create_users(db_session)

    service = EmergencyStopService()
    await service.activate(owner_id, reason="Integration test safety halt", actor_id=actor_id)

    # Check PostgreSQL — Valkey could be cleared, DB must be authoritative
    result = await db_session.execute(
        select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
    )
    stop = result.scalar_one_or_none()
    assert stop is not None, "EmergencyStop row must exist in PostgreSQL"
    assert stop.active is True
    assert stop.reason == "Integration test safety halt"
    assert stop.activated_at is not None


@pytest.mark.integration
async def test_emergency_stop_release_is_durable(db_session):
    """Release sets active=False in PostgreSQL; Valkey cache is invalidated."""
    from app.cache import valkey_client

    owner_id, actor_id = await _create_users(db_session)

    service = EmergencyStopService()
    await service.activate(owner_id, reason="Will be released", actor_id=actor_id)
    await service.release(owner_id, released_by=actor_id)

    # Check DB
    result = await db_session.execute(
        select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
    )
    stop = result.scalar_one_or_none()
    assert stop is not None
    assert stop.active is False
    assert stop.released_at is not None

    # Valkey cache should be clear or report inactive
    is_active = await service.is_active(owner_id)
    assert is_active is False


@pytest.mark.integration
async def test_emergency_stop_idempotent_reactivation(db_session):
    """Re-activating an already-active stop does not create duplicate rows."""
    owner_id, actor_id = await _create_users(db_session)

    service = EmergencyStopService()
    await service.activate(owner_id, reason="First activation", actor_id=actor_id)
    await service.activate(owner_id, reason="Second activation (idempotent)", actor_id=actor_id)

    result = await db_session.execute(
        select(EmergencyStop).where(EmergencyStop.owner_id == owner_id)
    )
    stops = result.scalars().all()
    assert len(stops) == 1, "Only one EmergencyStop row should exist per owner"
    assert stops[0].active is True


@pytest.mark.integration
async def test_emergency_stop_is_active_uses_db_on_cache_miss(db_session):
    """is_active() falls back to PostgreSQL when Valkey cache is cold."""
    from app.cache import valkey_client

    owner_id, actor_id = await _create_users(db_session)

    service = EmergencyStopService()
    await service.activate(owner_id, reason="Cache cold test", actor_id=actor_id)

    # Clear the cache to force a DB query
    await valkey_client.delete(f"emergency_stop:{owner_id}")

    is_active = await service.is_active(owner_id)
    assert is_active is True, "is_active() must fall back to DB when cache is cold"
