from typing import TypedDict


class OrderStatusResult(TypedDict):
    order_id: str
    found: bool
    status: str | None


MOCK_ORDERS = {
    "1001": "已付款，等待发货",
    "1002": "运输中，预计明天送达",
    "1003": "已完成",
    "1004": "已取消",
}


def lookup_order_status(order_id: str) -> OrderStatusResult:
    """查询订单状态，不依赖 FastAPI、LangGraph、LangChain 或 MCP。"""

    status = MOCK_ORDERS.get(order_id)

    if status is None:
        return {
            "order_id": order_id,
            "found": False,
            "status": None,
        }

    return {
        "order_id": order_id,
        "found": True,
        "status": status,
    }