from app.schemas import CreateTicketInput
from app.services.tickets import prepare_create_ticket


def test_prepare_create_ticket_returns_pending_action() -> None:
    command = CreateTicketInput(
        customer_id="c-100",
        title="订单迟迟未送达",
        priority="high",
    )

    result = prepare_create_ticket(command)

    assert result.ok is True
    assert result.data is not None
    assert result.data["status"] == "pending_confirmation"


def test_prepare_create_ticket_rejects_blocked_customer() -> None:
    command = CreateTicketInput(
        customer_id="blocked",
        title="订单迟迟未送达",
    )

    result = prepare_create_ticket(command)

    assert result.ok is False
    assert result.error_code == "CUSTOMER_BLOCKED"