from app.main import app


def test_admin_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/admin/threads/{thread_id}" in paths
    assert "get" in paths["/admin/threads/{thread_id}"]
    assert "delete" in paths["/admin/threads/{thread_id}"]

    assert "/admin/cache/orders/{order_id}" in paths
    assert "delete" in paths["/admin/cache/orders/{order_id}"]