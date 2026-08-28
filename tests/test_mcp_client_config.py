import sys

from app.mcp_client import (
    PROJECT_ROOT,
    create_mcp_server_config,
)


def test_mcp_server_uses_current_python_interpreter() -> None:
    config = create_mcp_server_config()

    assert config["order_mcp"]["command"] == sys.executable


def test_mcp_server_config_starts_order_server_module() -> None:
    config = create_mcp_server_config()

    assert config["order_mcp"]["args"] == [
        "-m",
        "mcp_servers.order_server",
    ]
    assert config["order_mcp"]["cwd"] == str(PROJECT_ROOT)
    assert config["order_mcp"]["env"] == {
        "PYTHONUTF8": "1",
    }