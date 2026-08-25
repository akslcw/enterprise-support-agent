import asyncio

from app.mcp_client import load_mcp_tools

async def main() -> None:
    tools = await load_mcp_tools()

    print("发现的 MCP Tools：")

    for tool in tools:
        print(f"- {tool.name}: {tool.description}")

    order_tool = next(
        tool for tool in tools if tool.name == "order_get_status"
    )

    result = await order_tool.ainvoke({"order_id": "1002"})

    print("\n调用 order_get_status 的结果：")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
