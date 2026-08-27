import pytest
from pydantic import ValidationError

from app.supervisor import route_after_supervisor


@pytest.mark.parametrize(
    "next_agent",
    [
        "order_agent",
        "knowledge_agent",
        "ticket_agent",
        "unsupported",
    ],
)
def test_route_after_supervisor_returns_known_agent(
    next_agent: str,
) -> None:
    state = {
        "messages": [],
        "pending_ticket": None,
        "approval_decision": None,
        "next_agent": next_agent,
    }

    assert route_after_supervisor(state) == next_agent


def test_route_after_supervisor_rejects_unknown_agent() -> None:
    state = {
        "messages": [],
        "pending_ticket": None,
        "approval_decision": None,
        "next_agent": "weather_agent",
    }

    with pytest.raises(ValidationError):
        route_after_supervisor(state)