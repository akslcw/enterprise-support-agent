import json
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from app.reliability import retry_read_operation
from app.cache import OrderStatusCache


def extract_order_status_payload(
    raw_result: Any,
) -> dict[str, Any]:
    """从 MCP Tool 返回内容中取出稳定的订单业务数据。"""

    if not isinstance(raw_result, list) or not raw_result:
        raise ValueError("MCP 订单 Tool 返回格式不正确。")

    first_item = raw_result[0]

    if not isinstance(first_item, dict):
        raise ValueError("MCP 订单 Tool 返回格式不正确。")

    text = first_item.get("text")

    if not isinstance(text, str):
        raise ValueError("MCP 订单 Tool 缺少文本结果。")

    payload = json.loads(text)

    if not isinstance(payload, dict):
        raise ValueError("MCP 订单 Tool 返回的业务数据不是对象。")

    return payload


def create_cached_order_status_tool(
    source_tool: BaseTool,
    cache: OrderStatusCache,
) -> StructuredTool:
    """用 Redis 包装原始 MCP 订单查询 Tool。"""

    if source_tool.name != "order_get_status":
        raise ValueError(
            "只能缓存 order_get_status Tool。"
        )

    async def cached_order_get_status(
        order_id: str,
    ) -> str:
        cached_payload = await cache.get(order_id)

        if cached_payload is not None:
            return json.dumps(
                cached_payload,
                ensure_ascii=False,
            )

        raw_result = await retry_read_operation(
            lambda: source_tool.ainvoke(
                {"order_id": order_id}
            ),
            operation_name="mcp_order_get_status",
        )

        payload = extract_order_status_payload(raw_result)

        await cache.set(order_id, payload)

        return json.dumps(
            payload,
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        coroutine=cached_order_get_status,
        name=source_tool.name,
        description=source_tool.description,
        args_schema=source_tool.args_schema,
        infer_schema=False,
    )