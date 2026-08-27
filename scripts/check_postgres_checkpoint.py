import asyncio
import sys
from typing import Annotated, TypedDict
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.settings import postgres_connection_string


class PersistenceTestState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def create_persistence_test_graph(checkpointer):
    builder = StateGraph(PersistenceTestState)

    def finish(_: PersistenceTestState) -> dict:
        """最小节点：不生成回复，只让 LangGraph 写入一次 checkpoint。"""

        return {}

    builder.add_node("finish", finish)
    builder.add_edge(START, "finish")
    builder.add_edge("finish", END)

    return builder.compile(checkpointer=checkpointer)


def thread_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


async def main() -> None:
    thread_id = f"stage08-persistence-{uuid4().hex[:8]}"
    config = thread_config(thread_id)

    print(f"本次验证 thread_id：{thread_id}")

    # 第一条消息：使用第一个数据库连接写入。
    async with AsyncPostgresSaver.from_conn_string(
        postgres_connection_string()
    ) as first_checkpointer:
        await first_checkpointer.setup()

        first_graph = create_persistence_test_graph(
            first_checkpointer
        )

        await first_graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="这是写入 PostgreSQL 的第一条消息"
                    )
                ]
            },
            config=config,
        )

    print("第一条消息已写入，第一条数据库连接已关闭。")

    # 第二条消息：新建连接后继续同一个 thread_id。
    async with AsyncPostgresSaver.from_conn_string(
        postgres_connection_string()
    ) as second_checkpointer:
        second_graph = create_persistence_test_graph(
            second_checkpointer
        )

        result = await second_graph.ainvoke(
            {
                "messages": [
                    HumanMessage(
                        content="这是重新连接后写入的第二条消息"
                    )
                ]
            },
            config=config,
        )

        messages = result["messages"]

    print(f"读取到消息数量：{len(messages)}")

    for index, message in enumerate(messages, start=1):
        print(f"消息 {index}：{message.content}")

    assert [
        str(message.content)
        for message in messages
    ] == [
        "这是写入 PostgreSQL 的第一条消息",
        "这是重新连接后写入的第二条消息",
    ]

    print("PostgreSQL Checkpoint 持久化验证成功。")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )

    asyncio.run(main())