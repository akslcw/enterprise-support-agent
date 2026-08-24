from app.tools import prepare_create_ticket


def test_ticket_tool_returns_pending_confirmation() -> None:
    result = prepare_create_ticket.invoke(
        {
            "customer_id": "c-100",
            "title": "订单迟迟未送达",
            "priority": "high",
        }
    )

    assert result["ok"] is True
    assert result["data"]["status"] == "pending_confirmation"


def test_ticket_tool_returns_business_error() -> None:
    result = prepare_create_ticket.invoke(
        {
            "customer_id": "blocked",
            "title": "订单迟迟未送达",
        }
    )

    assert result["ok"] is False
    assert result["error_code"] == "CUSTOMER_BLOCKED"