import pytest
from pydantic import ValidationError

from app.schemas import SupervisorDecision


@pytest.mark.parametrize(
    "next_agent",
    [
        "order_agent",
        "knowledge_agent",
        "ticket_agent",
        "unsupported",
    ],
)
def test_supervisor_decision_accepts_known_routes(
    next_agent: str,
) -> None:
    decision = SupervisorDecision(next_agent=next_agent)

    assert decision.next_agent == next_agent


def test_supervisor_decision_rejects_unknown_route() -> None:
    with pytest.raises(ValidationError):
        SupervisorDecision(next_agent="weather_agent")