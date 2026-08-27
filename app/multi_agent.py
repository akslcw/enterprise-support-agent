from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent import (
    capture_ticket_draft,
    request_ticket_approval,
    route_after_tools,
)
from app.domain_agents import (
    KNOWLEDGE_AGENT_PROMPT,
    ORDER_AGENT_PROMPT,
    TICKET_AGENT_PROMPT,
    build_domain_toolsets,
    create_domain_agent_node,
)
from app.supervisor import (
    create_supervisor_node,
    route_after_supervisor,
)


class MultiAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    pending_ticket: dict[str, Any] | None
    approval_decision: bool | None
    next_agent: str | None


def unsupported_agent(
    state: MultiAgentState,
) -> dict:
    return {
        "messages": [
            AIMessage(
                content=(
                    "当前服务不支持该问题。我是企业客服助手，"
                    "仅处理订单、工单、退款政策等企业支持问题。"
                )
            )
        ]
    }


def create_multi_agent_graph(
    *,
    mcp_tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
    supervisor_model: Any,
    order_model: Any,
    knowledge_model: Any,
    ticket_model: Any,
    domain_toolsets: dict[str, list[BaseTool]] | None = None,
):
    """创建候选多 Agent 图；调用方显式注入四个模型实例。"""

    toolsets = (
        domain_toolsets
        if domain_toolsets is not None
        else build_domain_toolsets(mcp_tools)
    )

    supervisor = create_supervisor_node(supervisor_model)
    order_agent = create_domain_agent_node(
        model=order_model,
        tools=toolsets["order_agent"],
        system_prompt=ORDER_AGENT_PROMPT,
    )
    knowledge_agent = create_domain_agent_node(
        model=knowledge_model,
        tools=toolsets["knowledge_agent"],
        system_prompt=KNOWLEDGE_AGENT_PROMPT,
    )
    ticket_agent = create_domain_agent_node(
        model=ticket_model,
        tools=toolsets["ticket_agent"],
        system_prompt=TICKET_AGENT_PROMPT,
    )

    builder = StateGraph(MultiAgentState)

    builder.add_node("supervisor", supervisor)

    builder.add_node("order_agent", order_agent)
    builder.add_node(
        "order_tools",
        ToolNode(toolsets["order_agent"]),
    )

    builder.add_node("knowledge_agent", knowledge_agent)
    builder.add_node(
        "knowledge_tools",
        ToolNode(toolsets["knowledge_agent"]),
    )

    builder.add_node("ticket_agent", ticket_agent)
    builder.add_node(
        "ticket_tools",
        ToolNode(toolsets["ticket_agent"]),
    )
    builder.add_node(
        "capture_ticket_draft",
        capture_ticket_draft,
    )
    builder.add_node(
        "request_ticket_approval",
        request_ticket_approval,
    )

    builder.add_node("unsupported", unsupported_agent)

    builder.add_edge(START, "supervisor")

    builder.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "order_agent": "order_agent",
            "knowledge_agent": "knowledge_agent",
            "ticket_agent": "ticket_agent",
            "unsupported": "unsupported",
        },
    )

    builder.add_conditional_edges(
        "order_agent",
        tools_condition,
        {
            "tools": "order_tools",
            "__end__": END,
        },
    )
    builder.add_edge("order_tools", "order_agent")

    builder.add_conditional_edges(
        "knowledge_agent",
        tools_condition,
        {
            "tools": "knowledge_tools",
            "__end__": END,
        },
    )
    builder.add_edge("knowledge_tools", "knowledge_agent")

    builder.add_conditional_edges(
        "ticket_agent",
        tools_condition,
        {
            "tools": "ticket_tools",
            "__end__": END,
        },
    )
    builder.add_edge("ticket_tools", "capture_ticket_draft")

    builder.add_conditional_edges(
        "capture_ticket_draft",
        route_after_tools,
        {
            "request_ticket_approval": "request_ticket_approval",
            "agent": "ticket_agent",
        },
    )
    builder.add_edge("request_ticket_approval", END)

    builder.add_edge("unsupported", END)

    return builder.compile(checkpointer=checkpointer)