import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage

from app.application.chat_service import ChatService
from app.schemas import (
    ChatCompletedResponse,
    PendingApprovalResponse,
)


class FakeGraph:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def ainvoke(
        self,
        graph_input: dict,
        config: dict,
    ) -> dict:
        self.calls.append(
            {
                "graph_input": graph_input,
                "config": config,
            }
        )
        return self.result


def test_chat_service_returns_completed_answer() -> None:
    graph = FakeGraph(
        {
            "messages": [
                AIMessage(content="订单 1002 正在运输中。"),
            ]
        }
    )

    result = asyncio.run(
        ChatService(graph).run(
            thread_id="chat-service-001",
            message="订单 1002 到哪里了？",
        )
    )

    assert isinstance(result, ChatCompletedResponse)
    assert result.answer == "订单 1002 正在运输中。"

    call = graph.calls[0]
    assert call["config"] == {
        "configurable": {
            "thread_id": "chat-service-001",
        }
    }
    assert call["graph_input"]["messages"][0].content == (
        "订单 1002 到哪里了？"
    )


def test_chat_service_returns_pending_approval() -> None:
    approval = {
        "type": "ticket_approval",
        "message": "请确认是否正式创建工单。",
        "draft": {
            "ticket_id": "T-DRAFT-001",
            "customer_id": "c-100",
            "title": "订单迟迟未送达",
            "priority": "high",
            "status": "pending_confirmation",
        },
    }
    graph = FakeGraph(
        {
            "__interrupt__": [
                SimpleNamespace(value=approval),
            ],
            "messages": [],
        }
    )

    result = asyncio.run(
        ChatService(graph).run(
            thread_id="chat-service-approval-001",
            message="为客户 c-100 创建工单：订单迟迟未送达",
        )
    )

    assert isinstance(result, PendingApprovalResponse)
    assert result.thread_id == "chat-service-approval-001"
    assert result.approval.draft.ticket_id == "T-DRAFT-001"