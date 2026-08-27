import pytest

from app.supervisor import create_supervisor_routing_graph


@pytest.mark.parametrize(
    "next_agent",
    [
        "order_agent",
        "knowledge_agent",
        "ticket_agent",
        "unsupported",
    ],
)
def test_supervisor_graph_reaches_expected_domain_agent(
    next_agent: str,
) -> None:
    graph = create_supervisor_routing_graph()

    result = graph.invoke(
        {
            "next_agent": next_agent,
            "handled_by": None,
        }
    )

    assert result["handled_by"] == next_agent