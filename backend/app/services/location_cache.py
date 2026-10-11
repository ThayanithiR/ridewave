import json
from datetime import UTC, datetime

import redis.asyncio as aioredis

from app.core.config import settings


class RedisLocationStore:
    def __init__(self, redis_url: str = settings.REDIS_URL):
        self.redis_url = redis_url
        self._client: aioredis.Redis | None = None

    async def get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=2.0,
            )
        return self._client

    async def update_driver_location(
        self,
        driver_id: str,
        latitude: float,
        longitude: float,
        h3_index: str,
        ttl_seconds: int = 60,
    ) -> bool:
        """Store ephemeral driver GPS ping in Redis with an auto-expiring TTL."""
        try:
            client = await self.get_client()
            payload = json.dumps(
                {
                    "driver_id": driver_id,
                    "latitude": latitude,
                    "longitude": longitude,
                    "h3_index": h3_index,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            # 1. Update driver specific key
            await client.set(f"driver:{driver_id}:location", payload, ex=ttl_seconds)
            # 2. Add driver to spatial cell bucket set
            await client.sadd(f"h3:{h3_index}:drivers", driver_id)
            await client.expire(f"h3:{h3_index}:drivers", ttl_seconds)
            return True
        except Exception:
            # Fallback gracefully if Redis is momentarily unavailable
            return False

    async def get_drivers_in_cells(self, cells: list[str]) -> list[str]:
        """Fetch all online driver IDs located within given H3 cell buckets."""
        try:
            client = await self.get_client()
            driver_ids = set()
            for cell in cells:
                members = await client.smembers(f"h3:{cell}:drivers")
                driver_ids.update(members)
            return list(driver_ids)
        except Exception:
            return []

    async def get_driver_location(self, driver_id: str) -> dict | None:
        """Get latest GPS coordinates of a specific driver."""
        try:
            client = await self.get_client()
            raw = await client.get(f"driver:{driver_id}:location")
            if raw:
                return json.loads(raw)
            return None
        except Exception:
            return None


redis_store = RedisLocationStore()
