import time
from typing import Optional

import httpx
from jose import JWTError, jwt

from app.api.errors import ApiError, ErrorCode
from app.auth.models import TokenClaims
from app.config import settings


class SupabaseAuth:
    def __init__(self):
        self._jwks_cache: Optional[dict] = None
        self._jwks_fetched_at: float = 0

    async def get_jwks(self) -> dict:
        if self._jwks_cache and (time.time() - self._jwks_fetched_at) < 3600:
            return self._jwks_cache

        async with httpx.AsyncClient() as client:
            response = await client.get(settings.SUPABASE_JWKS_URL)
            response.raise_for_status()
            self._jwks_cache = response.json()
            self._jwks_fetched_at = time.time()
            return self._jwks_cache

    async def verify_token(self, token: str) -> TokenClaims:
        jwks = await self.get_jwks()
        try:
            unverified_header = jwt.get_unverified_header(token)
            key = self._find_key(jwks, unverified_header.get("kid"))
            if not key:
                raise ApiError(ErrorCode.INVALID_TOKEN, "Invalid token key")

            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience="authenticated",
                issuer=f"{settings.SUPABASE_URL}/auth/v1",
            )
            return TokenClaims(**payload)
        except jwt.ExpiredSignatureError:
            raise ApiError(ErrorCode.EXPIRED_TOKEN, "Token has expired") from None
        except JWTError as e:
            raise ApiError(ErrorCode.INVALID_TOKEN, f"Invalid token: {str(e)}") from None

    def _find_key(self, jwks: dict, kid: str) -> Optional[dict]:
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        return None


supabase_auth = SupabaseAuth()
