from app.schemas import CreateTicketInput, ToolResult


def prepare_create_ticket(command: CreateTicketInput) -> ToolResult:
    if command.customer_id == "blocked":
        return ToolResult(
            ok=False,
            message="该客户当前不能创建工单",
            error_code="CUSTOMER_BLOCKED",
        )

    return ToolResult(
        ok=True,
        message="工单已准备创建，等待用户确认",
        data={
            "ticket_id": "T-DRAFT-10001",
            "status": "pending_confirmation",
            "customer_id": command.customer_id,
            "title": command.title,
            "priority": command.priority,
        },
    )