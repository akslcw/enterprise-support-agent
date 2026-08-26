from app.schemas import CreateTicketInput
from app.services.tickets import prepare_create_ticket
from app.schemas import TicketDraft
from app.services.tickets import create_ticket_from_draft


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

def test_create_ticket_from_draft_is_idempotent() -> None:
    draft = TicketDraft(
        ticket_id="T-DRAFT-IDEMPOTENT-1",
        customer_id="c-100",
        title="订单迟迟未送达",
        priority="high",
    )

    first_result = create_ticket_from_draft(draft)
    second_result = create_ticket_from_draft(draft)

    assert first_result.ok is True
    assert second_result.ok is True
    assert first_result.data is not None
    assert second_result.data is not None
    assert first_result.data["status"] == "created"
    assert first_result.data["ticket_id"] == second_result.data["ticket_id"]


def test_create_ticket_from_draft_rejects_blocked_customer() -> None:
    draft = TicketDraft(
        ticket_id="T-DRAFT-BLOCKED-1",
        customer_id="blocked",
        title="订单迟迟未送达",
        priority="normal",
    )

    result = create_ticket_from_draft(draft)

    assert result.ok is False
    assert result.error_code == "CUSTOMER_BLOCKED"