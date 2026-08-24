from langchain_core.messages import HumanMessage

from app.agent import graph


result = graph.invoke(
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