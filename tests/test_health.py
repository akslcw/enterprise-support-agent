from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health_response_contains_generated_trace_id() -> None:
    response = TestClient(app).get("/health")

    trace_id = response.headers["x-trace-id"]

    assert len(trace_id) == 32
    assert trace_id.isalnum()


def test_health_response_preserves_client_trace_id() -> None:
    response = TestClient(app).get(
        "/health",
        headers={
            "X-Trace-ID": "manual-trace-001",
        },
    )

    assert response.headers["x-trace-id"] == (
        "manual-trace-001"
    )

def test_health_replaces_invalid_client_trace_id() -> None:
    invalid_trace_id = "x" * 65

    response = TestClient(app).get(
        "/health",
        headers={
            "X-Trace-ID": invalid_trace_id,
        },
    )

    returned_trace_id = response.headers["x-trace-id"]

    assert returned_trace_id != invalid_trace_id
    assert len(returned_trace_id) == 32
    assert returned_trace_id.isalnum()