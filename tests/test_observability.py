import json
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    HTTP_LOGGER,
    JsonLogFormatter,
    is_valid_trace_id,
    resolve_trace_id,
)


def test_trace_id_validation_accepts_safe_characters() -> None:
    assert is_valid_trace_id("trace-001_abc") is True
    assert is_valid_trace_id("a" * 64) is True


def test_trace_id_validation_rejects_invalid_values() -> None:
    assert is_valid_trace_id("") is False
    assert is_valid_trace_id("trace id") is False
    assert is_valid_trace_id("a" * 65) is False


def test_resolve_trace_id_replaces_invalid_client_value() -> None:
    trace_id = resolve_trace_id("invalid trace id")

    assert trace_id != "invalid trace id"
    assert len(trace_id) == 32
    assert trace_id.isalnum()


class ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_json_log_formatter_includes_structured_fields() -> None:
    record = logging.LogRecord(
        name="enterprise_support.http",
        level=logging.INFO,
        pathname="test",
        lineno=1,
        msg="http_request_completed",
        args=(),
        exc_info=None,
    )
    record.trace_id = "trace-001"
    record.method = "GET"
    record.path = "/health"
    record.status_code = 200
    record.duration_ms = 1.25

    payload = json.loads(
        JsonLogFormatter().format(record)
    )

    assert payload["event"] == "http_request_completed"
    assert payload["trace_id"] == "trace-001"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.25


def test_health_request_writes_traceable_log_record() -> None:
    handler = ListHandler()
    HTTP_LOGGER.addHandler(handler)

    try:
        response = TestClient(app).get(
            "/health",
            headers={
                "X-Trace-ID": "trace-health-001",
            },
        )
    finally:
        HTTP_LOGGER.removeHandler(handler)

    assert response.status_code == 200

    record = handler.records[-1]

    assert record.getMessage() == "http_request_completed"
    assert record.trace_id == "trace-health-001"
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == 200
    assert record.duration_ms >= 0