from uuid import uuid4

from app.schemas import (
    CreateTicketInput,
    CreatedTicket,
    TicketDraft,
    ToolResult,
)


_created_tickets_by_draft: dict[str, CreatedTicket] = {}


def prepare_create_ticket(command: CreateTicketInput) -> ToolResult:
    """校验业务规则并生成工单草稿，不产生真正写操作。"""

    if command.customer_id == "blocked":
        return ToolResult(
            ok=False,
            message="该客户当前不能创建工单",
            error_code="CUSTOMER_BLOCKED",
        )

    draft = TicketDraft(
        ticket_id=f"T-DRAFT-{uuid4().hex[:10].upper()}",
        customer_id=command.customer_id,
        title=command.title,
        priority=command.priority,
        status="pending_confirmation",
    )

    return ToolResult(
        ok=True,
        message="工单已准备创建，等待用户确认",
        data=draft.model_dump(),
    )


def create_ticket_from_draft(draft: TicketDraft) -> ToolResult:
    """正式创建工单；同一草稿重复执行时返回同一结果。"""

    if draft.customer_id == "blocked":
        return ToolResult(
            ok=False,
            message="该客户当前不能创建工单",
            error_code="CUSTOMER_BLOCKED",
        )

    existing_ticket = _created_tickets_by_draft.get(draft.ticket_id)

    if existing_ticket is not None:
        return ToolResult(
            ok=True,
            message="该草稿对应的工单已创建，返回已有结果",
            data=existing_ticket.model_dump(),
        )

    created_ticket = CreatedTicket(
        ticket_id=f"T-{uuid4().hex[:10].upper()}",
        draft_ticket_id=draft.ticket_id,
        customer_id=draft.customer_id,
        title=draft.title,
        priority=draft.priority,
        status="created",
    )

    _created_tickets_by_draft[draft.ticket_id] = created_ticket

    return ToolResult(
        ok=True,
        message="工单已正式创建",
        data=created_ticket.model_dump(),
    )
