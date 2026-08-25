from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class MemoryTestState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def create_memory_test_graph():
    builder = StateGraph(MemoryTestState)

    def save_messages(_: MemoryTestState) -> dict:
        """这个节点不生成回答，只让 Graph 完成一次可被 checkpoint 的执行。"""

        return {}

    builder.add_node("save_messages", save_messages)
    builder.add_edge(START, "save_messages")
    builder.add_edge("save_messages", END)

    return builder.compile(checkpointer=InMemorySaver())


def message_contents(result: dict) -> list[str]:
    return [
        str(message.content)
        for message in result["messages"]
    ]


def test_same_thread_keeps_previous_messages():
    graph = create_memory_test_graph()

    config = {
        "configurable": {
            "thread_id": "thread-a",
        }
    }

    graph.invoke(
        {
            "messages": [
                HumanMessage(content="这是 thread-a 的第一条消息"),
            ]
        },
        config=config,
    )

    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="这是 thread-a 的第二条消息"),
            ]
        },
        config=config,
    )

    assert message_contents(result) == [
        "这是 thread-a 的第一条消息",
        "这是 thread-a 的第二条消息",
    ]


def test_different_thread_does_not_see_other_thread_messages():
    graph = create_memory_test_graph()

    thread_a_config = {
        "configurable": {
            "thread_id": "thread-a",
        }
    }
    thread_b_config = {
        "configurable": {
            "thread_id": "thread-b",
        }
    }

    graph.invoke(
        {
            "messages": [
                HumanMessage(content="这是 thread-a 的私有消息"),
            ]
        },
        config=thread_a_config,
    )

    thread_b_result = graph.invoke(
        {
            "messages": [
                HumanMessage(content="这是 thread-b 的第一条消息"),
            ]
        },
        config=thread_b_config,
    )

    assert message_contents(thread_b_result) == [
        "这是 thread-b 的第一条消息",
    ]

    thread_a_state = graph.get_state(thread_a_config)

    assert [
        str(message.content)
        for message in thread_a_state.values["messages"]
    ] == [
        "这是 thread-a 的私有消息",
    ]