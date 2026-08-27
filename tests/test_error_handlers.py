from fastapi.testclient import TestClient

from app.main import app


def test_unknown_route_returns_structured_not_found() -> None:
    response = TestClient(app).get(
        "/missing-route",
        headers={
            "X-Trace-ID": "trace-not-found-001",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "Not Found",
            "trace_id": "trace-not-found-001",
        }
    }
    assert response.headers["x-trace-id"] == (
        "trace-not-found-001"
    )


def test_invalid_chat_body_returns_safe_validation_error() -> None:
    response = TestClient(app).post(
        "/chat",
        headers={
            "X-Trace-ID": "trace-validation-001",
        },
        json={
            "thread_id": "",
            "message": "",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "请求参数不合法。",
            "trace_id": "trace-validation-001",
        }
    }

def test_invalid_thread_id_returns_structured_validation_error() -> None:
    response = TestClient(app).post(
        "/chat",
        headers={
            "X-Trace-ID": "trace-thread-id-001",
        },
        json={
            "thread_id": "../unsafe",
            "message": "订单 1002 到哪里了？",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "请求参数不合法。",
            "trace_id": "trace-thread-id-001",
        }
    }