import pytest
from pydantic import ValidationError

from app.schemas import (
    ChatCompletedResponse,
    PendingApprovalResponse,
    TicketApprovalCompletedResponse,
)


def test_chat_completed_response_has_fixed_status() -> None:
    response = ChatCompletedResponse(
        status="completed",
        answer="订单正在运输中。",
    )

    assert response.model_dump() == {
        "status": "completed",
        "answer": "订单正在运输中。",
    }


def test_pending_approval_response_validates_nested_draft() -> None:
    response = PendingApprovalResponse.model_validate(
        {
            "status": "pending_approval",
            "thread_id": "thread-001",
            "approval": {
                "type": "ticket_approval",
                "message": "请确认是否正式创建工单。",
                "draft": {
                    "ticket_id": "T-DRAFT-001",
                    "customer_id": "c-100",
                    "title": "订单迟迟未送达",
                    "priority": "high",
                    "status": "pending_confirmation",
                },
            },
        }
    )

    assert response.approval.draft.ticket_id == (
        "T-DRAFT-001"
    )


def test_pending_approval_response_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        PendingApprovalResponse.model_validate(
            {
                "status": "completed",
                "thread_id": "thread-001",
                "approval": {
                    "type": "ticket_approval",
                    "message": "请确认。",
                    "draft": {
                        "ticket_id": "T-DRAFT-001",
                        "customer_id": "c-100",
                        "title": "订单迟迟未送达",
                        "priority": "high",
                        "status": "pending_confirmation",
                    },
                },
            }
        )


def test_ticket_approval_completed_response_has_fixed_status() -> None:
    response = TicketApprovalCompletedResponse(
        status="completed",
        thread_id="thread-001",
        approved=True,
        answer="工单已创建。",
    )

    assert response.approved is True