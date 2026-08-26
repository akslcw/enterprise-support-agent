from types import SimpleNamespace

from app.main import get_interrupt_payload


def test_get_interrupt_payload_returns_approval_data() -> None:
    payload = {
        "type": "ticket_approval",
        "message": "请确认是否正式创建工单。",
        "draft": {
            "ticket_id": "T-DRAFT-001",
        },
    }

    result = {
        "__interrupt__": [
            SimpleNamespace(value=payload),
        ]
    }

    assert get_interrupt_payload(result) == payload


def test_get_interrupt_payload_returns_none_without_interrupt() -> None:
    assert get_interrupt_payload({"messages": []}) is None