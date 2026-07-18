
from typing import Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, ErrorCode
from app.auth.models import TokenClaims
from app.auth.supabase import supabase_auth
from app.database.session import get_db_session
from app.users.models import User
from app.users.service import UserService

security = HTTPBearer(auto_error=False)


async def get_current_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials:
        raise ApiError(ErrorCode.INVALID_TOKEN, "Missing authorization header", status_code=401)
    return credentials.credentials


async def get_token_claims(token: str = Depends(get_current_token)) -> TokenClaims:
    return await supabase_auth.verify_token(token)


async def get_current_user(
    claims: TokenClaims = Depends(get_token_claims),
    session: AsyncSession = Depends(get_db_session)
) -> User:
    user_service = UserService()
    user = await user_service.get_or_create_user(claims)
    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_db_session)
) -> Optional[User]:
    if not credentials:
        return None
    try:
        claims = await supabase_auth.verify_token(credentials.credentials)
        user_service = UserService()
        return await user_service.get_or_create_user(claims)
    except ApiError:
        return None
