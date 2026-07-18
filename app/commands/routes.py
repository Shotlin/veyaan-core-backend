from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user_context
from app.api.responses import ApiResponse, PaginatedResponse
from app.auth.user_context import UserContext
from app.commands.schemas import (
    CommandResponse,
    CreateCommandRequest,
    CreateCommandResponse,
    TaskResponse,
)
from app.commands.service import CommandService, TaskService

router = APIRouter(prefix="/commands", tags=["commands"])


async def get_command_service() -> CommandService:
    return CommandService()


@router.post(
    "", response_model=ApiResponse[CreateCommandResponse], status_code=status.HTTP_201_CREATED
)
async def create_command(
    request: CreateCommandRequest,
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    result = await service.create_command(request, current_user.id)
    return ApiResponse(data=result)


@router.get("/{command_id}", response_model=ApiResponse[CommandResponse])
async def get_command(
    command_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    from app.api.errors import ApiError, ErrorCode

    command = await service.get_command(command_id)
    if not command or str(command.device.owner_id) != str(current_user.id):
        raise ApiError(ErrorCode.COMMAND_NOT_FOUND, "Command not found", status_code=404)

    return ApiResponse(data=CommandResponse.model_validate(command))


@router.get("", response_model=ApiResponse[PaginatedResponse[CommandResponse]])
async def list_commands(
    device_id: UUID = Query(None, description="Filter by device"),
    state: str = Query(None, description="Filter by state"),
    risk_level: str = Query(None, description="Filter by risk level"),
    command_type: str = Query(None, description="Filter by command type"),
    start_date: datetime = Query(None, description="Filter by start date"),
    end_date: datetime = Query(None, description="Filter by end date"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    commands, total = await service.list_commands(
        owner_id=current_user.id,
        device_id=device_id,
        state=state,
        risk_level=risk_level,
        command_type=command_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    has_next = (page * page_size) < total
    has_prev = page > 1
    return ApiResponse(
        data=PaginatedResponse(
            items=[CommandResponse.model_validate(cmd) for cmd in commands],
            total=total,
            page=page,
            page_size=page_size,
            has_next=has_next,
            has_prev=has_prev,
        )
    )


@router.post("/{command_id}/cancel", response_model=ApiResponse[dict])
async def cancel_command(
    command_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    from app.api.errors import ApiError, ErrorCode

    success = await service.cancel_command(command_id, current_user.id)
    if not success:
        raise ApiError(
            ErrorCode.COMMAND_NOT_FOUND, "Command not found or cannot be cancelled", status_code=404
        )
    return ApiResponse(data={"cancelled": True})


@router.get("/{command_id}/events", response_model=ApiResponse[list])
async def get_command_events(
    command_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    events = await service.get_state_events(command_id, current_user.id)
    return ApiResponse(data=events)


@router.get("/{command_id}/task", response_model=ApiResponse[TaskResponse])
async def get_task(
    command_id: UUID,
    current_user: UserContext = Depends(get_current_user_context),
    service: CommandService = Depends(get_command_service),
):
    from app.api.errors import ApiError, ErrorCode

    command = await service.get_command(command_id)
    if not command or str(command.device.owner_id) != str(current_user.id):
        raise ApiError(ErrorCode.NOT_FOUND, "Task not found", status_code=404)

    task_service = TaskService()
    task = await task_service.get_task_by_command(command_id)
    if not task:
        raise ApiError(ErrorCode.NOT_FOUND, "Task not found", status_code=404)
    return ApiResponse(data=TaskResponse.model_validate(task))
