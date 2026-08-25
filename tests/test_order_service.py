from app.services.orders import lookup_order_status


def test_lookup_order_status_returns_existing_order():
    result = lookup_order_status("1002")

    assert result == {
        "order_id": "1002",
        "found": True,
        "status": "运输中，预计明天送达",
    }


def test_lookup_order_status_returns_not_found_result():
    result = lookup_order_status("9999")

    assert result == {
        "order_id": "9999",
        "found": False,
        "status": None,
    }