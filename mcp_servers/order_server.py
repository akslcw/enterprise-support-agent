from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from app.services.orders import lookup_order_status


class OrderStatusResponse(BaseModel):
    """order_get_status 的结构化 MCP 返回契约。"""

    order_id: str = Field(description="被查询的订单编号")
    found: bool = Field(description="是否找到该订单")
    status: str | None = Field(
        description="订单状态；未找到订单时为 null"
    )


mcp = FastMCP(
    name="order_mcp",
    instructions="这是企业客服订单查询服务，只提供只读订单状态查询。",
)


@mcp.tool(
    name="order_get_status",
    title="查询订单状态",
    description="根据订单编号查询订单当前状态。仅查询，不创建或修改订单。",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    structured_output=True,
)
def order_get_status(order_id: str) -> OrderStatusResponse:
    """根据订单编号返回结构化订单状态。"""

    return OrderStatusResponse(**lookup_order_status(order_id))


if __name__ == "__main__":
    mcp.run(transport="stdio")
