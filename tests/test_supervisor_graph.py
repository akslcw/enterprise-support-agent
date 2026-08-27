import asyncio

import pytest
from langchain_core.messages import HumanMessage

from app.schemas import SupervisorDecision
from app.supervisor import create_supervisor_graph


class FakeStructuredModel:
    def __init__(self, decision: SupervisorDecision):
        self.decision = decision
        self.received_messages = []

    def with_structured_output(self, schema, **kwargs):
        assert schema is SupervisorDecision
        assert kwargs == {
            "method": "function_calling",
        }
        return self

    async def ainvoke(self, messages):
        self.received_messages = messages
        return self.decision


@pytest.mark.parametrize(
    ("message", "next_agent"),
    [
        ("订单 1002 到哪里了？", "order_agent"),
        ("数字商品可以提现吗？", "knowledge_agent"),
        ("帮我创建投诉工单", "ticket_agent"),
        ("北京今天天气如何？", "unsupported"),
    ],
)
def test_supervisor_graph_routes_message_to_domain_agent(
    message: str,
    next_agent: str,
) -> None:
    model = FakeStructuredModel(
        SupervisorDecision(next_agent=next_agent)
    )
    graph = create_supervisor_graph(model)

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content=message),
                ],
                "next_agent": None,
                "handled_by": None,
            }
        )
    )

    assert result["next_agent"] == next_agent
    assert result["handled_by"] == next_agent
    assert model.received_messages[-1].content == message