from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, ErrorCode
from app.auth.supabase import supabase_auth
from app.auth.user_context import UserContext
from app.database.session import get_db_session
from app.users.repository import UserRepository

security = HTTPBearer(auto_error=False)


async def get_current_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise ApiError(ErrorCode.INVALID_TOKEN, "Missing authorization header", status_code=401)
    return credentials.credentials


async def get_current_user_context(
    token: str = Depends(get_current_token),
    session: AsyncSession = Depends(get_db_session),
) -> UserContext:
    claims = await supabase_auth.verify_token(token)
    repo = UserRepository(session)
    user = await repo.get_by_supabase_id(claims.sub)
    if not user:
        user = await repo.create(claims.sub, claims.email)
    if user.status == "suspended":
        raise ApiError(ErrorCode.FORBIDDEN, "Account suspended", status_code=403)
    return UserContext(
        id=user.id,
        supabase_user_id=user.supabase_user_id,
        email=user.email,
        status=user.status.value if hasattr(user.status, 'value') else str(user.status),
    )


async def get_optional_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> Optional[UserContext]:
    if not credentials:
        return None
    try:
        claims = await supabase_auth.verify_token(credentials.credentials)
        repo = UserRepository(session)
        user = await repo.get_by_supabase_id(claims.sub)
        if not user:
            user = await repo.create(claims.sub, claims.email)
        return UserContext(
            id=user.id,
            supabase_user_id=user.supabase_user_id,
            email=user.email,
            status=user.status.value if hasattr(user.status, 'value') else str(user.status),
        )
    except ApiError:
        return None
