import asyncio
import json

from app.cache import OrderStatusCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[dict] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int,
    ) -> None:
        self.values[key] = value
        self.set_calls.append(
            {
                "key": key,
                "value": value,
                "ttl_seconds": ex,
            }
        )

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)


def test_order_status_cache_returns_none_on_miss() -> None:
    cache = OrderStatusCache(FakeRedis())

    result = asyncio.run(cache.get("1002"))

    assert result is None


def test_order_status_cache_stores_payload_with_ttl() -> None:
    fake_redis = FakeRedis()
    cache = OrderStatusCache(
        fake_redis,
        ttl_seconds=60,
    )

    payload = {
        "order_id": "1002",
        "found": True,
        "status": "运输中，预计明天送达",
    }

    asyncio.run(cache.set("1002", payload))

    assert fake_redis.set_calls[0]["key"] == (
        "order-status:v1:1002"
    )
    assert fake_redis.set_calls[0]["ttl_seconds"] == 60
    assert json.loads(
        fake_redis.set_calls[0]["value"]
    ) == payload


def test_order_status_cache_reads_stored_payload() -> None:
    fake_redis = FakeRedis()
    cache = OrderStatusCache(fake_redis)

    payload = {
        "order_id": "1002",
        "found": True,
        "status": "运输中，预计明天送达",
    }

    asyncio.run(cache.set("1002", payload))
    result = asyncio.run(cache.get("1002"))

    assert result == payload


def test_order_status_cache_invalidates_payload() -> None:
    fake_redis = FakeRedis()
    cache = OrderStatusCache(fake_redis)

    asyncio.run(
        cache.set(
            "1002",
            {
                "order_id": "1002",
                "found": True,
                "status": "运输中，预计明天送达",
            },
        )
    )

    asyncio.run(cache.invalidate("1002"))
    result = asyncio.run(cache.get("1002"))

    assert result is None