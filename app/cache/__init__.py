from typing import Any, Optional

import valkey.asyncio as valkey

from app.config import settings


class ValkeyClient:
    def __init__(self):
        self.client: Optional[valkey.Valkey] = None

    async def connect(self):
        self.client = valkey.from_url(
            settings.VALKEY_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20
        )
        await self.client.ping()

    async def disconnect(self):
        if self.client:
            await self.client.close()

    async def set(self, key: str, value: Any, ttl: int = None) -> bool:
        if not self.client:
            return False
        full_key = f"{settings.VALKEY_KEY_PREFIX}{key}"
        if ttl is None:
            ttl = settings.VALKEY_DEFAULT_TTL
        if isinstance(value, (dict, list)):
            import json
            value = json.dumps(value)
        return await self.client.set(full_key, value, ex=ttl)

    async def get(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        full_key = f"{settings.VALKEY_KEY_PREFIX}{key}"
        value = await self.client.get(full_key)
        if value is None:
            return None
        try:
            import json
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def delete(self, key: str) -> bool:
        if not self.client:
            return False
        full_key = f"{settings.VALKEY_KEY_PREFIX}{key}"
        return await self.client.delete(full_key) > 0

    async def exists(self, key: str) -> bool:
        if not self.client:
            return False
        full_key = f"{settings.VALKEY_KEY_PREFIX}{key}"
        return await self.client.exists(full_key) > 0

    async def increment(self, key: str, ttl: int = None) -> int:
        if not self.client:
            return 0
        full_key = f"{settings.VALKEY_KEY_PREFIX}{key}"
        if ttl is None:
            ttl = settings.VALKEY_DEFAULT_TTL
        pipe = self.client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, ttl)
        results = await pipe.execute()
        return results[0]

    async def rate_limit_check(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """Returns (allowed, current_count, remaining)"""
        if not self.client:
            return True, 0, limit
        full_key = f"ratelimit:{settings.VALKEY_KEY_PREFIX}{key}"
        pipe = self.client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, window)
        pipe.ttl(full_key)
        results = await pipe.execute()
        current = results[0]
        remaining = max(0, limit - current)
        return current <= limit, current, remaining


valkey_client = ValkeyClient()
