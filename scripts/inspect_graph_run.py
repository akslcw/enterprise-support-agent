import asyncio

from langchain_core.messages import HumanMessage

from app.agent import create_graph
from app.mcp_client import load_mcp_tools


async def main() -> None:
    mcp_tools = await load_mcp_tools()
    graph = create_graph(mcp_tools)

    result = await graph.ainvoke(
        {
            "messages": [
                HumanMessage(content="订单 1002 到哪里了？"),
            ]
        }
    )

    for index, message in enumerate(result["messages"], start=1):
        print(f"\n===== Message {index} =====")
        print(f"type: {message.type}")
        print(f"content: {message.content}")

        tool_calls = getattr(message, "tool_calls", None)

        if tool_calls:
            print(f"tool_calls: {tool_calls}")

        tool_name = getattr(message, "name", None)

        if tool_name:
            print(f"tool_name: {tool_name}")


if __name__ == "__main__":
    asyncio.run(main())