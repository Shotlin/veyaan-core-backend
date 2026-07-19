from typing import Any, Optional

import valkey.asyncio as valkey

from app.config import settings


class ValkeyClient:
    def __init__(self):
        self.client: Optional[valkey.Valkey] = None

    async def connect(self):
        self.client = valkey.from_url(
            settings.VALKEY_URL, encoding="utf-8", decode_responses=True, max_connections=20
        )
        await self.client.ping()

    async def disconnect(self):
        if self.client:
            await self.client.close()

    def _prefix(self, key: str) -> str:
        return f"{settings.VALKEY_KEY_PREFIX}{key}"

    async def get(self, key: str) -> Optional[Any]:
        if not self.client:
            return None
        value = await self.client.get(self._prefix(key))
        if value is None:
            return None
        try:
            import json

            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def get_str(self, key: str) -> Optional[str]:
        if not self.client:
            return None
        return await self.client.get(self._prefix(key))

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if not self.client:
            return False
        full_key = self._prefix(key)
        if ttl is None:
            ttl = settings.VALKEY_DEFAULT_TTL
        if isinstance(value, (dict, list)):
            import json

            value = json.dumps(value)
        return await self.client.set(full_key, value, ex=ttl)

    async def delete(self, key: str) -> bool:
        if not self.client:
            return False
        return await self.client.delete(self._prefix(key)) > 0

    async def exists(self, key: str) -> bool:
        if not self.client:
            return False
        return await self.client.exists(self._prefix(key)) > 0

    async def getdel(self, key: str) -> Any:
        """Atomically GET and DELETE a key.

        Returns the value if the key existed, None otherwise.
        Decodes JSON values the same way as get().
        """
        if not self.client:
            return None
        value = await self.client.getdel(self._prefix(key))
        if value is None:
            return None
        try:
            import json

            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    async def increment(self, key: str, ttl: Optional[int] = None) -> int:
        if not self.client:
            return 0
        full_key = self._prefix(key)
        if ttl is None:
            ttl = settings.VALKEY_DEFAULT_TTL
        pipe = self.client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, ttl)
        results = await pipe.execute()
        return results[0]

    async def set_hash(self, key: str, mapping: dict, ttl: Optional[int] = None) -> bool:
        if not self.client:
            return False
        full_key = self._prefix(key)
        if ttl is None:
            ttl = settings.VALKEY_DEFAULT_TTL
        await self.client.hset(full_key, mapping=mapping)
        await self.client.expire(full_key, ttl)
        return True

    async def get_hash(self, key: str) -> Optional[dict]:
        if not self.client:
            return None
        return await self.client.hgetall(self._prefix(key))

    async def delete_hash(self, key: str) -> bool:
        if not self.client:
            return False
        return await self.client.delete(self._prefix(key)) > 0

    async def ping(self) -> bool:
        if not self.client:
            return False
        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    async def rate_limit_check(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        if not self.client:
            return True, 0, limit
        full_key = f"ratelimit:{self._prefix(key)}"
        pipe = self.client.pipeline()
        pipe.incr(full_key)
        pipe.expire(full_key, window)
        pipe.ttl(full_key)
        results = await pipe.execute()
        current = results[0]
        remaining = max(0, limit - current)
        return current <= limit, current, remaining


valkey_client = ValkeyClient()
