from typing import Any

from langgraph.types import Command

from app.reliability import run_with_timeout
from app.schemas import TicketApprovalCompletedResponse
from app.settings import agent_timeout_seconds


class PendingApprovalNotFoundError(Exception):
    """指定会话不存在待处理的人工审批。"""


def thread_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


class TicketApprovalService:
    """处理工单审批恢复这一业务用例。"""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def has_pending_interrupt(
        self,
        thread_id: str,
    ) -> bool:
        state = await self._graph.aget_state(
            thread_config(thread_id)
        )

        return any(task.interrupts for task in state.tasks)

    async def resume(
        self,
        thread_id: str,
        approved: bool,
    ) -> TicketApprovalCompletedResponse:
        if not await self.has_pending_interrupt(thread_id):
            raise PendingApprovalNotFoundError

        result = await run_with_timeout(
            self._graph.ainvoke(
                Command(resume={"approved": approved}),
                config=thread_config(thread_id),
            ),
            operation_name="ticket_approval_resume",
            timeout_seconds=agent_timeout_seconds(),
        )

        final_message = result["messages"][-1]

        return TicketApprovalCompletedResponse(
            status="completed",
            thread_id=thread_id,
            approved=approved,
            answer=str(final_message.content),
        )