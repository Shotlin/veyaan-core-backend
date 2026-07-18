from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update

from app.api.errors import ApiError, ErrorCode
from app.commands.models import Command, CommandState, CommandStateEvent, Task, TaskState
from app.commands.registry import command_registry
from app.commands.repository import CommandRepository
from app.commands.schemas import CreateCommandRequest, CreateCommandResponse
from app.commands.state_machine import StateTransitionError, transition_command
from app.database.session import get_db_session_context as get_db_session
from app.devices.repository import DeviceRepository
from app.emergency_stop.service import EmergencyStopService
from app.events import subjects
from app.events.outbox import OutboxRepository


class CommandService:
    def __init__(self):
        pass

    async def create_command(
        self, request: CreateCommandRequest, owner_id: UUID
    ) -> CreateCommandResponse:
        async with get_db_session() as session:
            repo = CommandRepository(session)
            device_repo = DeviceRepository(session)

            device = await device_repo.get_device(request.device_id)
            if not device or str(device.owner_id) != str(owner_id):
                raise ApiError(ErrorCode.DEVICE_NOT_FOUND, "Device not found", status_code=404)

            if device.trust_status.value != "trusted":
                raise ApiError(ErrorCode.DEVICE_REVOKED, "Device is not trusted", status_code=403)

            emergency_stop_service = EmergencyStopService()
            if await emergency_stop_service.is_active(owner_id):
                raise ApiError(
                    ErrorCode.EMERGENCY_STOP_ACTIVE,
                    "Emergency stop is active. Cannot create new commands.",
                    status_code=423,
                )

            existing = await repo.get_by_idempotency_key(request.device_id, request.idempotency_key)
            if existing:
                # GAP-P1-3: Conflict detection — same key + different command_type is a conflict
                if existing.command_type != request.command_type:
                    raise ApiError(
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "Idempotency key already used with a different command type",
                        status_code=409,
                    )
                task = await repo.get_task(existing.id)
                return CreateCommandResponse(
                    command_id=existing.id,
                    task_id=task.id if task else UUID(int=0),
                    state=existing.state,
                    requires_approval=existing.requires_approval,
                )

            definition = command_registry.get(request.command_type)
            if not definition:
                raise ApiError(
                    ErrorCode.INVALID_COMMAND_TYPE,
                    f"Unknown command type: {request.command_type}",
                    status_code=422,
                )

            definition.parameter_schema(**request.parameters)

            requires_approval = definition.requires_approval or request.requires_approval
            initial_state = CommandState.RECEIVED

            command = Command(
                device_id=request.device_id,
                command_type=request.command_type,
                parameters=request.parameters,
                risk_level=definition.risk_level.value,
                idempotency_key=request.idempotency_key,
                state=initial_state.value,
                requires_approval=requires_approval,
                delayed_execution_allowed=request.delayed_execution_allowed
                or definition.delayed_execution_allowed,
                expires_at=request.expires_at,
            )
            session.add(command)
            await session.flush()

            task = Task(command_id=command.id, state=TaskState.PENDING)
            session.add(task)
            await session.flush()

            event = CommandStateEvent(
                command_id=command.id,
                previous_state=None,
                new_state=initial_state.value,
                event_source="api",
            )
            session.add(event)

            approval_id = None
            decision_nonce = None

            if requires_approval:
                await transition_command(session, command.id, CommandState.VALIDATED, "api")
                await transition_command(session, command.id, CommandState.AWAITING_APPROVAL, "api")

                from app.approvals.repository import ApprovalRepository

                app_repo = ApprovalRepository(session)
                approval, decision_nonce = await app_repo.create_approval(
                    command_id=command.id,
                    owner_id=owner_id,
                    risk_level=command.risk_level,
                    action_title=f"Approve {command.command_type}",
                    action_description=f"Approve command {command.command_type} for device {command.device_id}",
                    expires_in_minutes=30,
                )
                approval_id = approval.id
            else:
                await transition_command(session, command.id, CommandState.VALIDATED, "api")
                await transition_command(session, command.id, CommandState.QUEUED, "api")
                outbox_repo = OutboxRepository(session)
                await outbox_repo.add_event(
                    event_type="command.queued",
                    aggregate_type="command",
                    aggregate_id=str(command.id),
                    subject=subjects.command_ready(str(device.id)),
                    payload={
                        "command_id": str(command.id),
                        "device_id": str(device.id),
                        "command_type": command.command_type,
                        "parameters": command.parameters,
                        "expires_at": command.expires_at.isoformat()
                        if command.expires_at
                        else None,
                        "risk_level": command.risk_level,
                    },
                )

            await session.commit()

            return CreateCommandResponse(
                command_id=command.id,
                task_id=task.id,
                state=command.state,
                requires_approval=requires_approval,
                approval_id=approval_id,
                decision_nonce=decision_nonce,
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

            try:
                await transition_command(session, command.id, CommandState.CANCELLED, "api")
                await session.commit()
                return True
            except StateTransitionError:
                return False

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

    async def get_state_events(self, command_id: UUID, owner_id: UUID):
        async with get_db_session() as session:
            repo = CommandRepository(session)
            command = await repo.get_by_id(command_id)
            if not command or str(command.device.owner_id) != str(owner_id):
                return []
            return await repo.get_state_events(command_id)

    async def approve_command(self, command_id: UUID) -> bool:
        async with get_db_session() as session:
            try:
                await transition_command(session, command_id, CommandState.APPROVED, "approval")
                await transition_command(session, command_id, CommandState.QUEUED, "approval")
                await session.commit()
                return True
            except StateTransitionError:
                return False

    async def reject_command(self, command_id: UUID) -> bool:
        async with get_db_session() as session:
            try:
                await transition_command(session, command_id, CommandState.REJECTED, "approval")
                await session.commit()
                return True
            except StateTransitionError:
                return False


class TaskService:
    async def get_task(self, task_id: UUID):
        async with get_db_session() as session:
            result = await session.execute(select(Task).where(Task.id == task_id))
            return result.scalar_one_or_none()

    async def get_task_by_command(self, command_id: UUID):
        async with get_db_session() as session:
            result = await session.execute(select(Task).where(Task.command_id == command_id))
            return result.scalar_one_or_none()

    async def update_task_state(
        self,
        task_id: UUID,
        state: TaskState,
        result_summary: str = None,
        error_code: str = None,
        error_message: str = None,
    ):
        async with get_db_session() as session:
            values = {
                "state": state.value,
                "started_at": datetime.now(timezone.utc) if state == TaskState.RUNNING else None,
                "finished_at": datetime.now(timezone.utc)
                if state in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED)
                else None,
                "result_summary": result_summary,
                "error_code": error_code,
                "error_message": error_message,
            }
            if state == TaskState.RUNNING:
                result = await session.execute(select(Task.attempt_count).where(Task.id == task_id))
                current_attempt = result.scalar_one_or_none()
                values["attempt_count"] = (current_attempt or 0) + 1

            await session.execute(update(Task).where(Task.id == task_id).values(**values))
            await session.commit()
