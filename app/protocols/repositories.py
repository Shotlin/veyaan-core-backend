"""
Repository protocol types for unit testing.

These Protocol classes define the interface contract for each repository.
Services depend on these protocols, not concrete implementations — enabling
full unit testing with simple mock objects without SQLAlchemy sessions.

Usage in tests:
    class FakeCommandRepository:
        async def get_by_id(self, command_id): return mock_command
        async def get_by_idempotency_key(self, device_id, key): return None
        ...

    service = CommandService(repo=FakeCommandRepository())
"""

from typing import Optional, Protocol
from uuid import UUID


class CommandRepositoryProtocol(Protocol):
    """Interface for CommandRepository — enables mock injection in unit tests."""

    async def get_by_id(self, command_id: UUID): ...
    async def get_by_idempotency_key(self, device_id: UUID, key: str): ...
    async def create(self, command) -> None: ...
    async def update_state(self, command_id: UUID, state: str, **fields) -> bool: ...
    async def list_commands(
        self, owner_id: UUID, state: Optional[str], page: int, page_size: int
    ) -> tuple: ...
    async def get_task(self, command_id: UUID): ...


class ApprovalRepositoryProtocol(Protocol):
    """Interface for ApprovalRepository."""

    async def get_approval(self, approval_id: UUID): ...
    async def create_approval(self, **kwargs) -> tuple: ...
    async def decide_approval(
        self, approval_id: UUID, owner_id: UUID, decision: str, nonce: str, note: Optional[str]
    ) -> tuple[bool, Optional[str]]: ...
    async def list_approvals(
        self, owner_id: UUID, status: Optional[str], risk_level: Optional[str],
        page: int, page_size: int
    ) -> tuple: ...
    async def expire_pending_approvals(self) -> int: ...


class DeviceRepositoryProtocol(Protocol):
    """Interface for DeviceRepository."""

    async def get_device(self, device_id: UUID): ...
    async def list_devices_by_owner(self, owner_id: UUID) -> list: ...
    async def revoke_device(self, device_id: UUID, owner_id: UUID) -> bool: ...
    async def update_last_seen(self, device_id: UUID) -> None: ...


class OutboxRepositoryProtocol(Protocol):
    """Interface for OutboxRepository."""

    async def add_event(
        self, event_type: str, aggregate_type: str, aggregate_id: str,
        subject: str, payload: dict
    ) -> None: ...
    async def get_pending_events(self, limit: int) -> list: ...
    async def mark_published(self, event_id: UUID) -> None: ...
    async def mark_failed(self, event_id: UUID, error: str) -> None: ...


class AuditRepositoryProtocol(Protocol):
    """Interface for AuditRepository."""

    async def create_log(self, **kwargs) -> None: ...
    async def list_logs(
        self, user_id: UUID, filters: dict, page: int, page_size: int
    ) -> tuple: ...


class UserRepositoryProtocol(Protocol):
    """Interface for UserRepository."""

    async def get_by_supabase_id(self, supabase_id: str): ...
    async def create(self, supabase_id: str, email: str): ...
    async def get_by_id(self, user_id: UUID): ...
