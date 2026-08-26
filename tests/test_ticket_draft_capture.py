import json

from langchain_core.messages import ToolMessage

from app.agent import capture_ticket_draft
from app.agent import capture_ticket_draft, route_after_tools


def test_capture_ticket_draft_saves_pending_ticket() -> None:
    tool_result = {
        "ok": True,
        "message": "工单已准备创建，等待用户确认",
        "data": {
            "ticket_id": "T-DRAFT-TEST-001",
            "customer_id": "c-100",
            "title": "订单迟迟未送达",
            "priority": "high",
            "status": "pending_confirmation",
        },
    }

    state = {
        "messages": [
            ToolMessage(
                content=json.dumps(tool_result),
                tool_call_id="call-test-001",
                name="prepare_create_ticket",
            )
        ],
        "pending_ticket": None,
    }

    result = capture_ticket_draft(state)

    assert result["pending_ticket"]["ticket_id"] == "T-DRAFT-TEST-001"
    assert result["pending_ticket"]["status"] == "pending_confirmation"


def test_capture_ticket_draft_ignores_failed_tool_result() -> None:
    tool_result = {
        "ok": False,
        "message": "该客户当前不能创建工单",
        "data": None,
        "error_code": "CUSTOMER_BLOCKED",
    }

    state = {
        "messages": [
            ToolMessage(
                content=json.dumps(tool_result),
                tool_call_id="call-test-002",
                name="prepare_create_ticket",
            )
        ],
        "pending_ticket": None,
    }

    assert capture_ticket_draft(state) == {}

def test_route_after_tools_goes_to_approval_when_draft_exists() -> None:
    state = {
        "messages": [],
        "pending_ticket": {
            "ticket_id": "T-DRAFT-TEST-001",
        },
    }

    assert route_after_tools(state) == "request_ticket_approval"


def test_route_after_tools_returns_to_agent_without_draft() -> None:
    state = {
        "messages": [],
        "pending_ticket": None,
    }

    assert route_after_tools(state) == "agent"