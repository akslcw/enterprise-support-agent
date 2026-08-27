import asyncio

from langchain_core.messages import HumanMessage

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