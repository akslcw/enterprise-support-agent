import json
from typing import Any

from redis.asyncio import Redis


class OrderStatusCache:
    """订单状态缓存：Redis 只保存可失效的查询副本。"""

    def __init__(
        self,
        redis: Redis,
        ttl_seconds: int = 60,
    ) -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def make_key(self, order_id: str) -> str:
        return f"order-status:v1:{order_id}"

    async def get(
        self,
        order_id: str,
    ) -> dict[str, Any] | None:
        raw_value = await self.redis.get(
            self.make_key(order_id)
        )

        if raw_value is None:
            return None

        return json.loads(raw_value)

    async def set(
        self,
        order_id: str,
        payload: dict[str, Any],
    ) -> None:
        await self.redis.set(
            self.make_key(order_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self.ttl_seconds,
        )

    async def invalidate(self, order_id: str) -> None:
        await self.redis.delete(
            self.make_key(order_id)
        )