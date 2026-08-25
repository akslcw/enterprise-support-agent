from mcp_servers.order_server import order_get_status


def test_order_mcp_tool_returns_existing_order() -> None:
    result = order_get_status("1002")

    assert result.model_dump() == {
        "order_id": "1002",
        "found": True,
        "status": "运输中，预计明天送达",
    }


def test_order_mcp_tool_returns_not_found_result() -> None:
    result = order_get_status("9999")

    assert result.model_dump() == {
        "order_id": "9999",
        "found": False,
        "status": None,
    }
