import asyncio

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from app.schemas import SupervisorDecision
from app.supervisor import create_supervisor_node


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


def test_supervisor_node_writes_next_agent_to_state() -> None:
    model = FakeStructuredModel(
        SupervisorDecision(next_agent="ticket_agent")
    )
    supervisor = create_supervisor_node(model)

    result = asyncio.run(
        supervisor(
            {
                "messages": [
                    HumanMessage(
                        content="帮我创建一个投诉工单"
                    )
                ]
            }
        )
    )

    assert result == {
        "next_agent": "ticket_agent",
    }
    assert model.received_messages[-1].content == "帮我创建一个投诉工单"


def test_supervisor_only_receives_latest_user_message() -> None:
    model = FakeStructuredModel(
        SupervisorDecision(next_agent="knowledge_agent")
    )
    supervisor = create_supervisor_node(model)

    asyncio.run(
        supervisor(
            {
                "messages": [
                    HumanMessage(
                        content="订单 1002 到哪里了？"
                    ),
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
                    ToolMessage(
                        content="运输中，预计明天送达",
                        tool_call_id="call-order-001",
                    ),
                    AIMessage(
                        content="订单正在运输中。"
                    ),
                    HumanMessage(
                        content="退款审核通过后多久到账？"
                    ),
                ]
            }
        )
    )

    assert len(model.received_messages) == 2
    assert model.received_messages[-1].content == (
        "退款审核通过后多久到账？"
    )
