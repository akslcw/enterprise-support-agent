import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from app.domain_agents import (
    KNOWLEDGE_AGENT_PROMPT,
    ORDER_AGENT_PROMPT,
    create_domain_agent_node,
)


@tool
def order_get_status(order_id: str) -> str:
    """查询订单状态。"""

    return order_id


class FakeToolModel:
    def __init__(self):
        self.bound_tools = []
        self.received_messages = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.received_messages = messages

        return AIMessage(
            content="订单 1002 正在运输中。"
        )


def test_order_agent_only_receives_order_tools() -> None:
    model = FakeToolModel()

    order_agent = create_domain_agent_node(
        model=model,
        tools=[order_get_status],
        system_prompt=ORDER_AGENT_PROMPT,
    )

    result = asyncio.run(
        order_agent(
            {
                "messages": [
                    HumanMessage(
                        content="订单 1002 到哪里了？"
                    )
                ]
            }
        )
    )

    assert [tool.name for tool in model.bound_tools] == [
        "order_get_status"
    ]
    assert "prepare_create_ticket" not in [
        tool.name
        for tool in model.bound_tools
    ]
    assert result["messages"][-1].content == (
        "订单 1002 正在运输中。"
    )
    assert model.received_messages[-1].content == (
        "订单 1002 到哪里了？"
    )




def test_knowledge_agent_prompt_forbids_unsupported_additions() -> None:
    assert "只包含 Tool 返回证据能够直接支持的结论" in (
        KNOWLEDGE_AGENT_PROMPT
    )
    assert "支付渠道差异" in KNOWLEDGE_AGENT_PROMPT
    assert "当前资料未说明" in KNOWLEDGE_AGENT_PROMPT
    assert "只回答用户当前问题所需要的最少规则" in KNOWLEDGE_AGENT_PROMPT
    assert "给出直接答案后立即结束" in KNOWLEDGE_AGENT_PROMPT
