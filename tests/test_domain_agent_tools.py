import pytest
from langchain_core.tools import tool

from app.domain_agents import build_domain_toolsets


@tool
def order_get_status(order_id: str) -> str:
    """查询订单状态。"""

    return order_id


@tool
def unrelated_mcp_tool() -> str:
    """不属于当前订单领域的 MCP Tool。"""

    return "unused"


def test_build_domain_toolsets_assigns_minimum_tools() -> None:
    toolsets = build_domain_toolsets(
        [
            order_get_status,
            unrelated_mcp_tool,
        ]
    )

    assert [tool.name for tool in toolsets["order_agent"]] == [
        "order_get_status"
    ]
    assert [tool.name for tool in toolsets["knowledge_agent"]] == [
        "search_knowledge"
    ]
    assert [tool.name for tool in toolsets["ticket_agent"]] == [
        "prepare_create_ticket"
    ]


def test_build_domain_toolsets_rejects_missing_order_tool() -> None:
    with pytest.raises(
        ValueError,
        match="未发现 order_get_status MCP Tool",
    ):
        build_domain_toolsets(
            [unrelated_mcp_tool]
        )