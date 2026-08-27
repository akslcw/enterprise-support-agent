import asyncio
import json
from typing import Any

from langchain_core.tools import tool

from app.cache import OrderStatusCache
from app.cached_tools import create_cached_order_status_tool


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        ex: int,
    ) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        return int(existed)


def create_source_tool(
    calls: list[str],
    failures_before_success: int = 0,
):
    @tool
    async def order_get_status(
        order_id: str,
    ) -> list[dict[str, Any]]:
        """根据订单编号查询订单当前状态。"""

        calls.append(order_id)

        if len(calls) <= failures_before_success:
            raise ConnectionError("temporary MCP failure")

        return [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "order_id": order_id,
                        "found": True,
                        "status": "运输中，预计明天送达",
                    },
                    ensure_ascii=False,
                ),
                "id": "temporary-mcp-result-id",
            }
        ]

    return order_get_status


def test_cached_tool_calls_source_on_cache_miss() -> None:
    calls: list[str] = []
    source_tool = create_source_tool(calls)
    cache = OrderStatusCache(FakeRedis())

    cached_tool = create_cached_order_status_tool(
        source_tool,
        cache,
    )

    result = asyncio.run(
        cached_tool.ainvoke({"order_id": "1002"})
    )

    assert json.loads(result) == {
        "order_id": "1002",
        "found": True,
        "status": "运输中，预计明天送达",
    }
    assert calls == ["1002"]


def test_cached_tool_skips_source_on_cache_hit() -> None:
    calls: list[str] = []
    source_tool = create_source_tool(calls)
    cache = OrderStatusCache(FakeRedis())

    cached_tool = create_cached_order_status_tool(
        source_tool,
        cache,
    )

    asyncio.run(
        cached_tool.ainvoke({"order_id": "1002"})
    )

    result = asyncio.run(
        cached_tool.ainvoke({"order_id": "1002"})
    )

    assert json.loads(result)["order_id"] == "1002"
    assert calls == ["1002"]


def test_cached_tool_preserves_tool_contract() -> None:
    calls: list[str] = []
    source_tool = create_source_tool(calls)
    cache = OrderStatusCache(FakeRedis())

    cached_tool = create_cached_order_status_tool(
        source_tool,
        cache,
    )

    assert cached_tool.name == "order_get_status"
    assert cached_tool.args_schema == source_tool.args_schema

def test_cached_tool_retries_transient_mcp_failure() -> None:
    calls: list[str] = []
    source_tool = create_source_tool(
        calls,
        failures_before_success=1,
    )
    cache = OrderStatusCache(FakeRedis())

    cached_tool = create_cached_order_status_tool(
        source_tool,
        cache,
    )

    result = asyncio.run(
        cached_tool.ainvoke({"order_id": "1002"})
    )

    assert json.loads(result)["found"] is True
    assert calls == ["1002", "1002"]
