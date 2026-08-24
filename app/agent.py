from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.llm import create_chat_model
from app.tools import get_order_status


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


model = create_chat_model().bind_tools([get_order_status])


def call_model(state: AgentState) -> dict:
    system_message = SystemMessage(
        content=(
            "你是企业客服助手。"
            "当用户询问指定订单的状态或进度时，必须调用 get_order_status 工具。"
            "不要编造订单状态。"
        )
    )

    response = model.invoke([system_message, *state["messages"]])

    return {"messages": [response]}


builder = StateGraph(AgentState)

builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode([get_order_status]))

builder.add_edge(START, "agent")

builder.add_conditional_edges(
    "agent",
    tools_condition,
    {
        "tools": "tools",
        "__end__": END,
    },
)

builder.add_edge("tools", "agent")

graph = builder.compile()