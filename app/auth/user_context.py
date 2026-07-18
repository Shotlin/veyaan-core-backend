from uuid import UUID

from pydantic import BaseModel


class UserContext(BaseModel):
    id: UUID
    supabase_user_id: str
    email: str
    status: str
    roles: frozenset[str] = frozenset()
