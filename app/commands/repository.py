from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.commands.models import Command, CommandState, CommandStateEvent, Task, TaskState
from app.commands.schemas import CreateCommandRequest
from app.devices.models import Device
from app.emergency_stop.models import EmergencyStop


class CommandRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_command(self, request: CreateCommandRequest, risk_level, requires_approval: bool) -> Command:
        command = Command(
            device_id=request.device_id,
            command_type=request.command_type,
            parameters=request.parameters,
            risk_level=risk_level,
            idempotency_key=request.idempotency_key,
            state=CommandState.AWAITING_APPROVAL if requires_approval else CommandState.QUEUED,
            requires_approval=requires_approval,
            delayed_execution_allowed=request.delayed_execution_allowed,
            expires_at=request.expires_at,
        )
        self.session.add(command)
        await self.session.flush()
        await self.session.refresh(command)
        return command

    async def create_task(self, command_id: UUID) -> Task:
        task = Task(command_id=command_id, state=TaskState.PENDING)
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def record_state_event(self, command_id: UUID, previous_state: Optional[CommandState], new_state: CommandState, event_source: str, metadata: dict = None) -> CommandStateEvent:
        event = CommandStateEvent(
            command_id=command_id,
            previous_state=previous_state,
            new_state=new_state,
            event_source=event_source,
            metadata=str(metadata) if metadata else None,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, command_id: UUID) -> Optional[Command]:
        result = await self.session.execute(
            select(Command)
            .options(selectinload(Command.task), selectinload(Command.device))
            .where(Command.id == command_id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, device_id: UUID, idempotency_key: str) -> Optional[Command]:
        result = await self.session.execute(
            select(Command)
            .where(Command.device_id == device_id, Command.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def update_state(self, command_id: UUID, new_state: CommandState, event_source: str, metadata: dict = None) -> bool:
        result = await self.session.execute(
            select(Command).where(Command.id == command_id)
        )
        command = result.scalar_one_or_none()
        if not command:
            return False

        previous_state = command.state
        command.state = new_state
        command.updated_at = datetime.now(timezone.utc)

        # Set timestamp fields based on state
        now = datetime.now(timezone.utc)
        if new_state == CommandState.DELIVERED:
            command.delivered_at = now
        elif new_state == CommandState.ACKNOWLEDGED:
            command.acknowledged_at = now
        elif new_state == CommandState.RUNNING:
            command.started_at = now
        elif new_state in (CommandState.SUCCEEDED, CommandState.FAILED, CommandState.CANCELLED, CommandState.EXPIRED, CommandState.TIMED_OUT):
            command.finished_at = now

        await self.session.flush()
        await self.record_state_event(command_id, previous_state, new_state, event_source, metadata)
        return True

    async def list_commands(
        self,
        owner_id: UUID = None,
        device_id: UUID = None,
        state: Optional[CommandState] = None,
        risk_level: Optional[str] = None,
        command_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Command], int]:
        query = select(Command).options(selectinload(Command.task))

        if owner_id:
            query = query.join(Device, Command.device_id == Device.id).where(Device.owner_id == owner_id)
        if device_id:
            query = query.where(Command.device_id == device_id)
        if state:
            query = query.where(Command.state == state)
        if risk_level:
            query = query.where(Command.risk_level == risk_level)
        if command_type:
            query = query.where(Command.command_type == command_type)
        if start_date:
            query = query.where(Command.created_at >= start_date)
        if end_date:
            query = query.where(Command.created_at <= end_date)

        query = query.order_by(Command.created_at.desc())

        # Count total
        count_query = select(Command.id)
        if owner_id:
            count_query = count_query.join(Device, Command.device_id == Device.id).where(Device.owner_id == owner_id)
        if device_id:
            count_query = count_query.where(Command.device_id == device_id)
        if state:
            count_query = count_query.where(Command.state == state)
        if risk_level:
            count_query = count_query.where(Command.risk_level == risk_level)
        if command_type:
            count_query = count_query.where(Command.command_type == command_type)
        if start_date:
            count_query = count_query.where(Command.created_at >= start_date)
        if end_date:
            count_query = count_query.where(Command.created_at <= end_date)

        total_result = await self.session.execute(count_query)
        total = len(total_result.scalars().all())

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(query)
        commands = result.scalars().all()

        return list(commands), total

    async def get_state_events(self, command_id: UUID) -> list[CommandStateEvent]:
        result = await self.session.execute(
            select(CommandStateEvent)
            .where(CommandStateEvent.command_id == command_id)
            .order_by(CommandStateEvent.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_pending_commands(self, limit: int = 100) -> list[Command]:
        """Get commands ready for delivery (QUEUED state), excluding those with emergency stop active."""
        result = await self.session.execute(
            select(Command)
            .join(Device, Command.device_id == Device.id)
            .outerjoin(EmergencyStop, Device.owner_id == EmergencyStop.owner_id)
            .where(Command.state == CommandState.QUEUED)
            .where(or_(Command.expires_at.is_(None), Command.expires_at > datetime.now(timezone.utc)))
            .where(or_(EmergencyStop.active.is_(None), ~EmergencyStop.active))
            .order_by(Command.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_acknowledged_commands(self, limit: int = 100) -> list[Command]:
        """Get commands that were acknowledged but not yet marked as running."""
        result = await self.session.execute(
            select(Command)
            .where(Command.state == CommandState.ACKNOWLEDGED)
            .order_by(Command.acknowledged_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())
