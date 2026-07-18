from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.supabase import TokenClaims, supabase_auth
from app.database.session import get_db_session as get_session
from app.users.repository import UserRepository
from app.users.service import UserService

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenClaims:
    if not credentials:
        from app.api.errors import ApiError, ErrorCode
        raise ApiError(ErrorCode.INVALID_TOKEN, "Missing authorization header", status_code=401)

    return await supabase_auth.verify_token(credentials.credentials)


async def get_user_service() -> UserService:
    async with get_session() as session:
        repo = UserRepository(session)
        yield UserService(repo)


async def get_device_repo():
    async with get_session() as session:
        from app.devices.repository import DeviceRepository
        yield DeviceRepository(session)


async def get_command_repo():
    async with get_session() as session:
        from app.commands.repository import CommandRepository
        yield CommandRepository(session)
