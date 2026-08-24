from app.tools import get_order_status


def test_get_order_status_returns_known_order() -> None:
    result = get_order_status.invoke({"order_id": "1002"})

    assert result == "运输中，预计明天送达"


def test_get_order_status_returns_safe_message_for_unknown_order() -> None:
    result = get_order_status.invoke({"order_id": "9999"})

    assert result == "未找到该订单"