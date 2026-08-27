import asyncio

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.llm import create_chat_model
from app.mcp_client import load_mcp_tools
from app.multi_agent import create_multi_agent_graph


CASES = [
    (
        "preview-multi-order",
        "订单 1002 到哪里了？",
    ),
    (
        "preview-multi-knowledge",
        "退款审核通过后多久到账？",
    ),
    (
        "preview-multi-ticket",
        "为客户 c-100 创建工单：订单迟迟未送达",
    ),
    (
        "preview-multi-unsupported",
        "北京今天天气怎么样？",
    ),
]


async def main() -> None:
    mcp_tools = await load_mcp_tools()

    graph = create_multi_agent_graph(
        mcp_tools=mcp_tools,
        checkpointer=InMemorySaver(),
        supervisor_model=create_chat_model(
            thinking="disabled"
        ),
        order_model=create_chat_model(),
        knowledge_model=create_chat_model(),
        ticket_model=create_chat_model(),
    )

    for thread_id, message in CASES:
        result = await graph.ainvoke(
            {
                "messages": [
                    HumanMessage(content=message),
                ],
                "pending_ticket": None,
                "approval_decision": None,
                "next_agent": None,
            },
            config={
                "configurable": {
                    "thread_id": thread_id,
                }
            },
        )

        print(f"问题：{message}")
        print(f"路由：{result['next_agent']}")

        interrupts = result.get("__interrupt__", [])

        if interrupts:
            payload = interrupts[0].value
            print("结果：等待人工审批")
            print(f"草稿：{payload['draft']}")
        else:
            print(
                "回答："
                f"{result['messages'][-1].content}"
            )

        print()


if __name__ == "__main__":
    asyncio.run(main())