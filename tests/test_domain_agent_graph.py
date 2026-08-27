import asyncio

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.tools import tool

from app.domain_agents import (
    ORDER_AGENT_PROMPT,
    create_domain_agent_graph,
)


@tool
def order_get_status(order_id: str) -> str:
    """查询订单状态。"""

    if order_id == "1002":
        return "运输中，预计明天送达"

    return "未找到该订单"


class FakeToolCallingModel:
    def __init__(self):
        self.calls = []
        self.responses = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "order_get_status",
                        "args": {"order_id": "1002"},
                        "id": "call-order-001",
                    }
                ],
            ),
            AIMessage(
                content="订单 1002 正在运输中，预计明天送达。"
            ),
        ]

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


def test_order_agent_runs_its_own_tool_loop() -> None:
    model = FakeToolCallingModel()

    graph = create_domain_agent_graph(
        model=model,
        tools=[order_get_status],
        system_prompt=ORDER_AGENT_PROMPT,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="订单 1002 到哪里了？"
                    )
                ]
            }
        )
    )

    assert result["messages"][-1].content == (
        "订单 1002 正在运输中，预计明天送达。"
    )

    second_model_call = model.calls[1]

    assert any(
        isinstance(message, ToolMessage)
        and message.name == "order_get_status"
        and message.content == "运输中，预计明天送达"
        for message in second_model_call
    )