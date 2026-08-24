from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.llm import create_chat_model
from app.tools import get_order_status, prepare_create_ticket


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]

tools = [
    get_order_status,
    prepare_create_ticket,
]

model = create_chat_model().bind_tools(tools)


def call_model(state: AgentState) -> dict:
    system_message = SystemMessage(
    content=(
        "你是企业客服助手。"
        "当用户询问指定订单的状态或进度时，调用 get_order_status。"
        "当用户要求创建工单，并提供客户 ID 与明确的问题描述时，调用 "
        "prepare_create_ticket。问题描述可以直接作为工单标题。"
        "如果用户已经表达了具体问题，不要再次追问工单标题。"
        "不要编造订单状态、客户信息或工单结果。"
    )
)

    response = model.invoke([system_message, *state["messages"]])

    return {"messages": [response]}


builder = StateGraph(AgentState)

builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))

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