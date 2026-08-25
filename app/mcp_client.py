from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_EXECUTABLE = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def create_mcp_client() -> MultiServerMCPClient:
    """创建到本地 MCP Server 的连接配置。"""

    return MultiServerMCPClient(
        {
            "order_mcp": {
                "transport": "stdio",
                "command": str(PYTHON_EXECUTABLE),
                "args": ["-m", "mcp_servers.order_server"],
                "cwd": str(PROJECT_ROOT),
                "env": {
                    "PYTHONUTF8": "1",
                },
            }
        }
    )


async def load_mcp_tools() -> list[BaseTool]:
    """从已配置的 MCP Server 动态发现并转换为 LangChain Tool。"""

    client = create_mcp_client()

    return await client.get_tools(server_name="order_mcp")