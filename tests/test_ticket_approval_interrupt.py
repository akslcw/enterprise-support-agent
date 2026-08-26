from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command

from app.agent import request_ticket_approval


class ApprovalState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    pending_ticket: dict[str, Any] | None
    approval_decision: bool | None

def create_approval_test_graph():
    builder = StateGraph(ApprovalState)

    builder.add_node(
        "request_ticket_approval",
        request_ticket_approval,
    )
    builder.add_edge(START, "request_ticket_approval")
    builder.add_edge("request_ticket_approval", END)

    return builder.compile(checkpointer=InMemorySaver())


def make_draft(ticket_id: str) -> dict[str, Any]:
    return {
        "ticket_id": ticket_id,
        "customer_id": "c-100",
        "title": "订单迟迟未送达",
        "priority": "high",
        "status": "pending_confirmation",
    }


def test_interrupt_then_resume_with_approval() -> None:
    graph = create_approval_test_graph()
    config = {"configurable": {"thread_id": "approval-yes"}}

    interrupted = graph.invoke(
        {
            "pending_ticket": make_draft("T-DRAFT-YES"),
            "approval_decision": None,
            "messages": [],
        },
        config=config,
    )

    payload = interrupted["__interrupt__"][0].value

    assert payload["type"] == "ticket_approval"
    assert payload["draft"]["ticket_id"] == "T-DRAFT-YES"

    resumed = graph.invoke(
        Command(resume={"approved": True}),
        config=config,
    )

    assert resumed["pending_ticket"] is None
    assert resumed["approval_decision"] is True
    assert "已正式创建" in resumed["messages"][-1].content


def test_interrupt_then_resume_with_rejection() -> None:
    graph = create_approval_test_graph()
    config = {"configurable": {"thread_id": "approval-no"}}

    graph.invoke(
        {
            "pending_ticket": make_draft("T-DRAFT-NO"),
            "approval_decision": None,
            "messages": [],
        },
        config=config,
    )

    resumed = graph.invoke(
        Command(resume={"approved": False}),
        config=config,
    )

    assert resumed["pending_ticket"] is None
    assert resumed["approval_decision"] is False
    assert resumed["messages"][-1].content == "工单草稿已取消，未执行正式创建。"