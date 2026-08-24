from langchain_core.tools import tool


@tool
def get_order_status(order_id: str) -> str:
    """根据订单编号查询当前订单状态。仅在用户询问指定订单进度时使用。"""
    mock_orders = {
        "1001": "已付款，等待发货",
        "1002": "运输中，预计明天送达",
        "1003": "已完成",
        "1004": "已取消",
    }

    return mock_orders.get(order_id, "未找到该订单")