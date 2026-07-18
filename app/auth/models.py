from typing import Any

from pydantic import BaseModel


class TokenClaims(BaseModel):
    sub: str
    email: str
    role: str = "authenticated"
    user_metadata: dict[str, Any] = {}
    app_metadata: dict[str, Any] = {}
    aud: str = "authenticated"
    exp: int
    iat: int
    iss: str

    @property
    def user_id(self) -> str:
        return self.sub
