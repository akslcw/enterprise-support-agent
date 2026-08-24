import pytest
from pydantic import ValidationError

from app.schemas import CreateTicketInput


def test_create_ticket_input_uses_default_priority() -> None:
    ticket = CreateTicketInput(
        customer_id="c-100",
        title="订单迟迟未送达",
    )

    assert ticket.priority == "normal"


def test_create_ticket_input_rejects_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        CreateTicketInput(
            customer_id="c-100",
            title="订单迟迟未送达",
            priority="urgent",
        )