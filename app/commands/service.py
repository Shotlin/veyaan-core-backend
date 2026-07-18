from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.models import Command, CommandState, CommandStateEvent, Task, TaskState
from app.commands.registry import command_registry
from app.commands.repository import CommandRepository
from app.commands.schemas import CreateCommandRequest, CreateCommandResponse
from app.database.session import get_db_session
from app.emergency_stop.service import EmergencyStopService
from app.events.nats_client import nats_client


class CommandService:
    def __init__(self):
        pass

    async def create_command(self, request: CreateCommandRequest, owner_id: UUID) -> CreateCommandResponse:
        async with get_db_session() as session:
            repo = CommandRepository(session)

            # Check emergency stop before creating command
            emergency_stop_service = EmergencyStopService()
            if await emergency_stop_service.is_active(owner_id):
                raise ValueError("Emergency stop is active. Cannot create new commands.")

            # Check idempotency
            existing = await repo.get_by_idempotency_key(request.device_id, request.idempotency_key)
            if existing:
                task = await repo.get_task(existing.id)
                return CreateCommandResponse(
                    command_id=existing.id,
                    task_id=task.id if task else UUID(int=0),
                    state=existing.state,
                    requires_approval=existing.requires_approval,
                )

            # Validate command type
            definition = command_registry.get(request.command_type)
            if not definition:
                raise ValueError(f"Unknown command type: {request.command_type}")

            # Validate parameters
            definition.parameter_schema(**request.parameters)

            # Determine risk and approval
            requires_approval = definition.requires_approval or request.requires_approval
            initial_state = CommandState.AWAITING_APPROVAL if requires_approval else CommandState.QUEUED

            # Create command
            command = Command(
                device_id=request.device_id,
                command_type=request.command_type,
                parameters=request.parameters,
                risk_level=definition.risk_level,
                idempotency_key=request.idempotency_key,
                state=initial_state,
                requires_approval=requires_approval,
                delayed_execution_allowed=request.delayed_execution_allowed or definition.delayed_execution_allowed,
                expires_at=request.expires_at,
            )
            session.add(command)
            await session.flush()

            # Create task
            task = Task(command_id=command.id, state=TaskState.PENDING)
            session.add(task)
            await session.flush()

            # Record state event
            event = CommandStateEvent(
                command_id=command.id,
                previous_state=None,
                new_state=initial_state,
                event_source="api",
            )
            session.add(event)

            # If queued (not awaiting approval), publish to NATS
            if initial_state == CommandState.QUEUED:
                await self._publish_command(session, command)

            await session.commit()

            return CreateCommandResponse(
                command_id=command.id,
                task_id=task.id,
                state=command.state,
                requires_approval=requires_approval,
            )

    async def get_command(self, command_id: UUID) -> Optional[Command]:
        async with get_db_session() as session:
            repo = CommandRepository(session)
            return await repo.get_by_id(command_id)

    async def cancel_command(self, command_id: UUID, owner_id: UUID) -> bool:
        async with get_db_session() as session:
            repo = CommandRepository(session)
            command = await repo.get_by_id(command_id)
            if not command or str(command.device.owner_id) != str(owner_id):
                return False

            if command.state not in (CommandState.QUEUED, CommandState.AWAITING_APPROVAL, CommandState.APPROVED):
                return False

            await repo.update_state(command_id, CommandState.CANCELLED, "api")
            await session.commit()
            return True

    async def list_commands(
        self,
        owner_id: UUID,
        device_id: UUID = None,
        state: str = None,
        risk_level: str = None,
        command_type: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
        page: int = 1,
        page_size: int = 20,
    ):
        async with get_db_session() as session:
            repo = CommandRepository(session)
            commands, total = await repo.list_commands(
                owner_id=owner_id,
                device_id=device_id,
                state=CommandState(state) if state else None,
                risk_level=risk_level,
                command_type=command_type,
                start_date=start_date,
                end_date=end_date,
                page=page,
                page_size=page_size,
            )
            return commands, total

    async def get_state_events(self, command_id: UUID):
        async with get_db_session() as session:
            repo = CommandRepository(session)
            return await repo.get_state_events(command_id)

    async def _publish_command(self, session: AsyncSession, command: Command):
        """Publish command to NATS for delivery to device."""
        import json

        payload = {
            "command_id": str(command.id),
            "device_id": str(command.device_id),
            "command_type": command.command_type,
            "parameters": command.parameters,
            "expires_at": command.expires_at.isoformat() if command.expires_at else None,
            "risk_level": command.risk_level.value,
            "trace_id": f"cmd-{command.id}",
        }

        await nats_client.publish(
            "veyaan.commands.deliver",
            json.dumps(payload).encode(),
            headers={"command_id": str(command.id)},
        )

        # Update state to DELIVERED
        await session.execute(
            update(Command)
            .where(Command.id == command.id)
            .values(state=CommandState.DELIVERED, delivered_at=datetime.now(timezone.utc))
        )
        await session.flush()

        # Record event
        event = CommandStateEvent(
            command_id=command.id,
            previous_state=CommandState.QUEUED,
            new_state=CommandState.DELIVERED,
            event_source="api",
        )
        session.add(event)


class TaskService:
    async def get_task(self, task_id: UUID):
        async with get_db_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            return result.scalar_one_or_none()

    async def get_task_by_command(self, command_id: UUID):
        async with get_db_session() as session:
            result = await session.execute(select(Task).where(Task.command_id == command_id))
            return result.scalar_one_or_none()

    async def update_task_state(self, task_id: UUID, state: TaskState, result_summary: str = None, error_code: str = None, error_message: str = None):
        async with get_db_session() as session:
            # Increment attempt count when transitioning to RUNNING
            values = {
                "state": state,
                "started_at": datetime.now(timezone.utc) if state == TaskState.RUNNING else None,
                "finished_at": datetime.now(timezone.utc) if state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED) else None,
                "result_summary": result_summary,
                "error_code": error_code,
                "error_message": error_message,
            }
            if state == TaskState.RUNNING:
                # Increment attempt count
                result = await session.execute(select(Task.attempt_count).where(Task.id == task_id))
                current_attempt = result.scalar_one_or_none()
                values["attempt_count"] = (current_attempt or 0) + 1

            await session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(**values)
            )
            await session.commit()
