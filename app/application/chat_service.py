from typing import Any

from langchain_core.messages import HumanMessage

from app.reliability import run_with_timeout
from app.schemas import (
    ChatCompletedResponse,
    PendingApprovalResponse,
    TicketApprovalPayload,
)
from app.settings import agent_timeout_seconds


class ChatService:
    """执行一次客服对话用例，不依赖 FastAPI Request。"""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    async def run(
        self,
        thread_id: str,
        message: str,
    ) -> ChatCompletedResponse | PendingApprovalResponse:
        result = await run_with_timeout(
            self._graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(content=message),
                    ]
                },
                config={
                    "configurable": {
                        "thread_id": thread_id,
                    }
                },
            ),
            operation_name="chat_graph",
            timeout_seconds=agent_timeout_seconds(),
        )

        approval = get_interrupt_payload(result)

        if approval is not None:
            return PendingApprovalResponse(
                status="pending_approval",
                thread_id=thread_id,
                approval=TicketApprovalPayload.model_validate(
                    approval
                ),
            )

        final_message = result["messages"][-1]

        return ChatCompletedResponse(
            status="completed",
            answer=str(final_message.content),
        )


def get_interrupt_payload(
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """提取 Graph 暂停时需要交给人工审批者的内容。"""

    interrupts = result.get("__interrupt__", [])

    if not interrupts:
        return None

    payload = interrupts[0].value

    if not isinstance(payload, dict):
        return None

    return payload