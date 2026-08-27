import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.multi_agent import create_multi_agent_graph
from app.schemas import SupervisorDecision


@tool
def order_get_status(order_id: str) -> str:
    """查询订单状态。"""

    if order_id == "1002":
        return "运输中，预计明天送达"

    return "未找到该订单"

@tool
def search_knowledge(question: str) -> str:
    """查询测试知识库。"""

    return "来源：refund-policy.md\n退款审核通过后 3 到 5 个工作日到账。"


@tool
def prepare_create_ticket(
    customer_id: str,
    title: str,
) -> dict:
    """准备测试工单草稿。"""

    return {
        "ok": True,
        "message": "测试草稿",
        "data": {
            "ticket_id": "T-DRAFT-TEST-001",
            "customer_id": customer_id,
            "title": title,
            "priority": "normal",
            "status": "pending_confirmation",
        },
    }


class FakeSupervisorModel:
    def __init__(self, next_agent: str):
        self.next_agent = next_agent

    def with_structured_output(self, schema, **kwargs):
        assert schema is SupervisorDecision
        assert kwargs == {
            "method": "function_calling",
        }
        return self

    async def ainvoke(self, messages):
        return SupervisorDecision(
            next_agent=self.next_agent
        )

class FakeDomainModel:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.bound_tools = []

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0)


def test_multi_agent_graph_routes_to_order_agent_and_tool() -> None:
    order_model = FakeDomainModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "order_get_status",
                        "args": {"order_id": "1002"},
                        "id": "call-multi-order-001",
                    }
                ],
            ),
            AIMessage(
                content="订单 1002 正在运输中，预计明天送达。"
            ),
        ]
    )
    knowledge_model = FakeDomainModel([])
    ticket_model = FakeDomainModel([])

    graph = create_multi_agent_graph(
        mcp_tools=[order_get_status],
        checkpointer=InMemorySaver(),
        supervisor_model=FakeSupervisorModel("order_agent"),
        order_model=order_model,
        knowledge_model=knowledge_model,
        ticket_model=ticket_model,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="订单 1002 到哪里了？"
                    )
                ],
                "pending_ticket": None,
                "approval_decision": None,
                "next_agent": None,
            },
            config={
                "configurable": {
                    "thread_id": "multi-agent-order-test",
                }
            },
        )
    )

    assert result["next_agent"] == "order_agent"
    assert result["messages"][-1].content == (
        "订单 1002 正在运输中，预计明天送达。"
    )
    assert len(order_model.calls) == 2
    assert knowledge_model.calls == []
    assert ticket_model.calls == []

def test_multi_agent_graph_routes_to_knowledge_agent_and_tool() -> None:
    knowledge_model = FakeDomainModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_knowledge",
                        "args": {
                            "question": "退款审核通过后多久到账？"
                        },
                        "id": "call-multi-knowledge-001",
                    }
                ],
            ),
            AIMessage(
                content=(
                    "根据 refund-policy.md，退款审核通过后 "
                    "3 到 5 个工作日到账。"
                )
            ),
        ]
    )
    order_model = FakeDomainModel([])
    ticket_model = FakeDomainModel([])

    graph = create_multi_agent_graph(
        mcp_tools=[],
        domain_toolsets={
            "order_agent": [order_get_status],
            "knowledge_agent": [search_knowledge],
            "ticket_agent": [prepare_create_ticket],
        },
        checkpointer=InMemorySaver(),
        supervisor_model=FakeSupervisorModel(
            "knowledge_agent"
        ),
        order_model=order_model,
        knowledge_model=knowledge_model,
        ticket_model=ticket_model,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="退款审核通过后多久到账？"
                    )
                ],
                "pending_ticket": None,
                "approval_decision": None,
                "next_agent": None,
            },
            config={
                "configurable": {
                    "thread_id": "multi-agent-knowledge-test",
                }
            },
        )
    )

    assert result["next_agent"] == "knowledge_agent"
    assert result["messages"][-1].content == (
        "根据 refund-policy.md，退款审核通过后 "
        "3 到 5 个工作日到账。"
    )
    assert len(knowledge_model.calls) == 2
    assert order_model.calls == []
    assert ticket_model.calls == []

def test_multi_agent_graph_pauses_for_ticket_approval() -> None:
    ticket_model = FakeDomainModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "prepare_create_ticket",
                        "args": {
                            "customer_id": "c-100",
                            "title": "订单迟迟未送达",
                        },
                        "id": "call-multi-ticket-001",
                    }
                ],
            )
        ]
    )
    order_model = FakeDomainModel([])
    knowledge_model = FakeDomainModel([])

    graph = create_multi_agent_graph(
        mcp_tools=[],
        domain_toolsets={
            "order_agent": [order_get_status],
            "knowledge_agent": [search_knowledge],
            "ticket_agent": [prepare_create_ticket],
        },
        checkpointer=InMemorySaver(),
        supervisor_model=FakeSupervisorModel(
            "ticket_agent"
        ),
        order_model=order_model,
        knowledge_model=knowledge_model,
        ticket_model=ticket_model,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "为客户 c-100 创建工单："
                            "订单迟迟未送达"
                        )
                    )
                ],
                "pending_ticket": None,
                "approval_decision": None,
                "next_agent": None,
            },
            config={
                "configurable": {
                    "thread_id": "multi-agent-ticket-test",
                }
            },
        )
    )

    payload = result["__interrupt__"][0].value

    assert result["next_agent"] == "ticket_agent"
    assert payload["type"] == "ticket_approval"
    assert payload["draft"]["ticket_id"] == (
        "T-DRAFT-TEST-001"
    )
    assert payload["draft"]["status"] == (
        "pending_confirmation"
    )

    # Ticket Agent 只调用一次“准备草稿”的 Tool，
    # 尚未获得人工确认，因此没有第二次模型调用。
    assert len(ticket_model.calls) == 1
    assert order_model.calls == []
    assert knowledge_model.calls == []

def test_multi_agent_graph_rejects_unsupported_request() -> None:
    order_model = FakeDomainModel([])
    knowledge_model = FakeDomainModel([])
    ticket_model = FakeDomainModel([])

    graph = create_multi_agent_graph(
        mcp_tools=[],
        domain_toolsets={
            "order_agent": [order_get_status],
            "knowledge_agent": [search_knowledge],
            "ticket_agent": [prepare_create_ticket],
        },
        checkpointer=InMemorySaver(),
        supervisor_model=FakeSupervisorModel(
            "unsupported"
        ),
        order_model=order_model,
        knowledge_model=knowledge_model,
        ticket_model=ticket_model,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="北京今天天气怎么样？"
                    )
                ],
                "pending_ticket": None,
                "approval_decision": None,
                "next_agent": None,
            },
            config={
                "configurable": {
                    "thread_id": "multi-agent-unsupported-test",
                }
            },
        )
    )

    assert result["next_agent"] == "unsupported"
    assert "当前服务不支持该问题" in (
        result["messages"][-1].content
    )
    assert order_model.calls == []
    assert knowledge_model.calls == []
    assert ticket_model.calls == []