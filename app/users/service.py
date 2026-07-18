from typing import Optional
from uuid import UUID

from app.auth.models import TokenClaims
from app.database.session import get_db_session_context as session_scope
from app.users.models import User
from app.users.repository import UserRepository


class UserService:
    def __init__(self):
        pass

    async def get_or_create_user(self, claims: TokenClaims) -> User:
        async with session_scope() as session:
            repo = UserRepository(session)
            user = await repo.get_by_supabase_id(claims.sub)
            if not user:
                user = await repo.create(
                    supabase_user_id=claims.sub,
                    display_name=claims.user_metadata.get("full_name") or claims.email,
                    email=claims.email,
                )
            return user

    async def get_user(self, user_id: UUID) -> Optional[User]:
        async with session_scope() as session:
            repo = UserRepository(session)
            return await repo.get(user_id)
