from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateTicketInput(BaseModel):
    customer_id: str = Field(
        min_length=1,
        description="客户 ID",
    )
    title: str = Field(
        min_length=3,
        max_length=100,
        description="工单标题",
    )
    priority: Literal["low", "normal", "high"] = "normal"


class ToolResult(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] | None = None
    error_code: str | None = None

class TicketDraft(BaseModel):
    ticket_id: str
    customer_id: str
    title: str
    priority: Literal["low", "normal", "high"]
    status: Literal["pending_confirmation"] = "pending_confirmation"


class CreatedTicket(BaseModel):
    ticket_id: str
    draft_ticket_id: str
    customer_id: str
    title: str
    priority: Literal["low", "normal", "high"]
    status: Literal["created"]

SupervisorRoute = Literal[
    "order_agent",
    "knowledge_agent",
    "ticket_agent",
    "unsupported",
]

class SupervisorDecision(BaseModel):
    """Supervisor 可选择的下一处理节点。"""

    next_agent: SupervisorRoute = Field(
        description=(
            "根据用户当前请求选择唯一的下一处理节点。"
        )
    )