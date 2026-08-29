import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.application.ticket_approval_service import (
    PendingApprovalNotFoundError,
    TicketApprovalService,
)


class FakeGraph:
    def __init__(
        self,
        tasks: list,
        result: dict | None = None,
    ) -> None:
        self.tasks = tasks
        self.result = result or {"messages": []}
        self.state_calls: list[dict] = []
        self.invoke_calls: list[dict] = []

    async def aget_state(self, config: dict):
        self.state_calls.append(config)
        return SimpleNamespace(tasks=self.tasks)

    async def ainvoke(
        self,
        command,
        config: dict,
    ) -> dict:
        self.invoke_calls.append(
            {
                "command": command,
                "config": config,
            }
        )
        return self.result


def pending_task() -> SimpleNamespace:
    return SimpleNamespace(
        interrupts=(SimpleNamespace(value={}),)
    )


def test_service_detects_pending_approval() -> None:
    graph = FakeGraph(tasks=[pending_task()])

    result = asyncio.run(
        TicketApprovalService(graph).has_pending_interrupt(
            "approval-service-001"
        )
    )

    assert result is True
    assert graph.state_calls == [
        {
            "configurable": {
                "thread_id": "approval-service-001",
            }
        }
    ]


def test_service_resumes_approved_ticket() -> None:
    graph = FakeGraph(
        tasks=[pending_task()],
        result={
            "messages": [
                AIMessage(content="工单已正式创建。"),
            ]
        },
    )

    result = asyncio.run(
        TicketApprovalService(graph).resume(
            thread_id="approval-service-002",
            approved=True,
        )
    )

    assert result.status == "completed"
    assert result.thread_id == "approval-service-002"
    assert result.approved is True
    assert result.answer == "工单已正式创建。"
    assert graph.invoke_calls[0]["config"] == {
        "configurable": {
            "thread_id": "approval-service-002",
        }
    }


def test_service_rejects_resume_without_pending_approval() -> None:
    graph = FakeGraph(tasks=[])

    with pytest.raises(PendingApprovalNotFoundError):
        asyncio.run(
            TicketApprovalService(graph).resume(
                thread_id="approval-service-003",
                approved=False,
            )
        )

    assert graph.invoke_calls == []