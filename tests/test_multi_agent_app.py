from fastapi.testclient import TestClient

from app.main import app


def test_app_starts_with_multi_agent_graph() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

        node_names = set(
            client.app.state.graph.get_graph().nodes
        )

    assert response.status_code == 200
    assert node_names >= {
        "supervisor",
        "order_agent",
        "knowledge_agent",
        "ticket_agent",
        "request_ticket_approval",
        "unsupported",
    }