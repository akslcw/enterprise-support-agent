import sys
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_mcp_server_config() -> dict:
    """创建本地订单 MCP Server 的跨平台启动配置。"""

    return {
        "order_mcp": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_servers.order_server"],
            "cwd": str(PROJECT_ROOT),
            "env": {
                "PYTHONUTF8": "1",
            },
        }
    }


def create_mcp_client() -> MultiServerMCPClient:
    """创建到本地 MCP Server 的连接配置。"""

    return MultiServerMCPClient(
        create_mcp_server_config()
    )


async def load_mcp_tools() -> list[BaseTool]:
    """从已配置的 MCP Server 动态发现并转换为 LangChain Tool。"""

    client = create_mcp_client()

    return await client.get_tools(server_name="order_mcp")