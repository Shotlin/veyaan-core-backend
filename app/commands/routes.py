from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user
from app.api.responses import ApiResponse, PaginatedResponse
from app.commands.schemas import (
    CommandResponse,
    CreateCommandRequest,
    CreateCommandResponse,
    TaskResponse,
)
from app.commands.service import CommandService
from app.users.models import User

router = APIRouter(prefix="/commands", tags=["commands"])


async def get_command_service() -> CommandService:
    return CommandService()


@router.post("", response_model=ApiResponse[CreateCommandResponse], status_code=status.HTTP_201_CREATED)
async def create_command(
    request: CreateCommandRequest,
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    result = await service.create_command(request, current_user.id)
    return ApiResponse(data=result)


@router.get("/{command_id}", response_model=ApiResponse[CommandResponse])
async def get_command(
    command_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    command = await service.get_command(command_id)
    if not command:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.COMMAND_NOT_FOUND, "Command not found", status_code=404)

    # Verify ownership
    if str(command.device.owner_id) != str(current_user.id):
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.FORBIDDEN, "Not authorized", status_code=403)

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
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    # This would need to be implemented with proper filtering
    return ApiResponse(data=PaginatedResponse(
        items=[],
        total=0,
        page=page,
        page_size=page_size,
        has_next=False,
        has_prev=False,
    ))


@router.post("/{command_id}/cancel", response_model=ApiResponse[dict])
async def cancel_command(
    command_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    success = await service.cancel_command(command_id, current_user.id)
    if not success:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.COMMAND_NOT_FOUND, "Command not found or cannot be cancelled", status_code=404)
    return ApiResponse(data={"cancelled": True})


@router.get("/{command_id}/events", response_model=ApiResponse[list])
async def get_command_events(
    command_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    events = await service.get_state_events(command_id)
    return ApiResponse(data=events)


@router.get("/{command_id}/task", response_model=ApiResponse[TaskResponse])
async def get_task(
    command_id: UUID,
    current_user: User = Depends(get_current_user),
    service: CommandService = Depends(get_command_service),
):
    from app.commands.service import TaskService
    task_service = TaskService()
    task = await task_service.get_task_by_command(command_id)
    if not task:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.NOT_FOUND, "Task not found", status_code=404)
    return ApiResponse(data=TaskResponse.model_validate(task))
