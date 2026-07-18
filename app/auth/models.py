from typing import Any

from pydantic import BaseModel, Field


class TokenClaims(BaseModel):
    model_config = {"frozen": True}

    sub: str
    email: str
    role: str = "authenticated"
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    app_metadata: dict[str, Any] = Field(default_factory=dict)
    aud: str = "authenticated"
    exp: int
    iat: int
    iss: str

    @property
    def user_id(self) -> str:
        return self.sub
