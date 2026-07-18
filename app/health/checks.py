from typing import Any

from sqlalchemy import text

from app.cache import valkey_client
from app.database.connection import engine
from app.events.nats_client import nats_client


class HealthChecker:
    async def check_liveness(self) -> dict[str, Any]:
        return {"status": "alive", "service": "veyaan-api"}

    async def check_readiness(self) -> dict[str, Any]:
        checks = {}
        all_ready = True

        # Database
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["database"] = {"status": "ready"}
        except Exception as e:
            checks["database"] = {"status": "not_ready", "error": str(e)}
            all_ready = False

        # NATS
        try:
            if nats_client.nc and nats_client.nc.is_connected:
                checks["nats"] = {"status": "ready"}
            else:
                checks["nats"] = {"status": "not_ready", "error": "Not connected"}
                all_ready = False
        except Exception as e:
            checks["nats"] = {"status": "not_ready", "error": str(e)}
            all_ready = False

        # Valkey
        try:
            if valkey_client.client:
                await valkey_client.client.ping()
                checks["valkey"] = {"status": "ready"}
            else:
                checks["valkey"] = {"status": "not_ready", "error": "Not connected"}
                all_ready = False
        except Exception as e:
            checks["valkey"] = {"status": "not_ready", "error": str(e)}
            all_ready = False

        return {"ready": all_ready, "checks": checks}

    async def check_detailed(self) -> dict[str, Any]:
        readiness = await self.check_readiness()

        # Add more detailed info
        detailed = {**readiness, "service": "veyaan-api", "version": "0.1.0"}

        # NATS streams info
        try:
            if nats_client.js:
                streams = await nats_client.js.streams_info()
                detailed["nats_streams"] = [s.config.name for s in streams]
        except Exception:
            detailed["nats_streams"] = []

        # Valkey info
        try:
            if valkey_client.client:
                info = await valkey_client.client.info("memory")
                detailed["valkey_memory"] = info.get("used_memory_human", "unknown")
        except Exception:
            detailed["valkey_memory"] = "unknown"

        return detailed


health_checker = HealthChecker()
