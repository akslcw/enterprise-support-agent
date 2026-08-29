from typing import Any, TypedDict

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import END, START, StateGraph

from app.schemas import (
    SupervisorDecision,
    SupervisorRoute,
)

SUPERVISOR_PROMPT = """
你是企业客服系统的 Supervisor，只负责选择下一位处理者，不回答用户问题，
不调用任何 Tool，也不创建或修改任何业务数据。

根据用户当前请求选择唯一的 next_agent：

- order_agent：订单状态、物流进度、订单查询。
- knowledge_agent：退款政策、售后规则、知识库文档事实。
- ticket_agent：创建工单、投诉、问题反馈、工单相关操作。
- unsupported：天气、新闻、医疗、法律、投资等企业客服范围外的问题。

必须选择一个已有值。
"""


def get_current_user_message(
    messages: list[AnyMessage],
) -> HumanMessage:
    """返回本轮最新的用户消息，隔离历史领域 Tool 消息。"""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message

    raise ValueError("Supervisor 至少需要一条用户消息。")


def create_supervisor_node(model: Any):
    """将支持 structured output 的模型包装成 LangGraph 节点。"""

    structured_model = model.with_structured_output(
        SupervisorDecision,
        method="function_calling",
    )

    async def supervisor(state: dict[str, Any]) -> dict[str, Any]:
        current_user_message = get_current_user_message(
            state["messages"]
        )

        decision = await structured_model.ainvoke(
            [
                SystemMessage(content=SUPERVISOR_PROMPT),
                current_user_message,
            ]
        )

        return {
            "next_agent": decision.next_agent,
        }

    return supervisor

class SupervisorRoutingState(TypedDict):
    next_agent: SupervisorRoute | None
    handled_by: SupervisorRoute | None

class SupervisorGraphState(TypedDict):
    messages: list[AnyMessage]
    next_agent: SupervisorRoute | None
    handled_by: SupervisorRoute | None


def route_after_supervisor(
    state: dict[str, Any],
) -> SupervisorRoute:
    """校验 Supervisor 决策后，返回 LangGraph 的下一个节点名。"""

    decision = SupervisorDecision.model_validate(
        {
            "next_agent": state.get("next_agent"),
        }
    )

    return decision.next_agent


def create_domain_marker(
    agent_name: SupervisorRoute,
):
    """学习阶段使用：记录实际进入了哪个领域节点。"""

    def domain_agent(
        state: SupervisorRoutingState,
    ) -> dict:
        return {
            "handled_by": agent_name,
        }

    return domain_agent


def create_supervisor_routing_graph():
    """构建不调用真实模型和 Tool 的最小分流图。"""

    builder = StateGraph(SupervisorRoutingState)

    builder.add_node("supervisor", lambda state: {})
    builder.add_node(
        "order_agent",
        create_domain_marker("order_agent"),
    )
    builder.add_node(
        "knowledge_agent",
        create_domain_marker("knowledge_agent"),
    )
    builder.add_node(
        "ticket_agent",
        create_domain_marker("ticket_agent"),
    )
    builder.add_node(
        "unsupported",
        create_domain_marker("unsupported"),
    )

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

    builder.add_edge("order_agent", END)
    builder.add_edge("knowledge_agent", END)
    builder.add_edge("ticket_agent", END)
    builder.add_edge("unsupported", END)

    return builder.compile()

def create_supervisor_graph(model: Any):
    """构建含 Supervisor 模型节点的实验性多 Agent 分流图。"""

    builder = StateGraph(SupervisorGraphState)

    builder.add_node(
        "supervisor",
        create_supervisor_node(model),
    )
    builder.add_node(
        "order_agent",
        create_domain_marker("order_agent"),
    )
    builder.add_node(
        "knowledge_agent",
        create_domain_marker("knowledge_agent"),
    )
    builder.add_node(
        "ticket_agent",
        create_domain_marker("ticket_agent"),
    )
    builder.add_node(
        "unsupported",
        create_domain_marker("unsupported"),
    )

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

    builder.add_edge("order_agent", END)
    builder.add_edge("knowledge_agent", END)
    builder.add_edge("ticket_agent", END)
    builder.add_edge("unsupported", END)

    return builder.compile()
