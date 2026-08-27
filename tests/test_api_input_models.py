import pytest
from pydantic import ValidationError

from app.main import ApprovalRequest, ChatRequest


@pytest.mark.parametrize(
    "thread_id",
    [
        "thread-001",
        "user_abc",
        "a" * 100,
    ],
)
def test_chat_request_accepts_safe_thread_id(
    thread_id: str,
) -> None:
    request = ChatRequest(
        thread_id=thread_id,
        message="订单 1002 到哪里了？",
    )

    assert request.thread_id == thread_id


@pytest.mark.parametrize(
    "thread_id",
    [
        "",
        "thread id",
        "../thread",
        "a" * 101,
    ],
)
def test_chat_request_rejects_unsafe_thread_id(
    thread_id: str,
) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            thread_id=thread_id,
            message="订单 1002 到哪里了？",
        )


def test_approval_request_uses_same_thread_id_boundary() -> None:
    with pytest.raises(ValidationError):
        ApprovalRequest(
            thread_id="bad/thread",
            approved=True,
        )