from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AnyMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from app.tools import prepare_create_ticket, search_knowledge


def build_domain_toolsets(
    mcp_tools: list[BaseTool],
) -> dict[str, list[BaseTool]]:
    """按领域为 Agent 分配最小必要 Tool 集。"""

    order_tools = [
        tool
        for tool in mcp_tools
        if tool.name == "order_get_status"
    ]

    if not order_tools:
        raise ValueError(
            "未发现 order_get_status MCP Tool"
        )

    return {
        "order_agent": order_tools,
        "knowledge_agent": [search_knowledge],
        "ticket_agent": [prepare_create_ticket],
    }

ORDER_AGENT_PROMPT = """
你是订单领域客服 Agent。

你只能处理订单状态、物流进度和订单查询。
当需要订单事实时，调用已分配的订单查询 Tool。
不得回答退款政策，不得创建或修改工单，不得编造订单信息。
"""

KNOWLEDGE_AGENT_PROMPT = """
你是知识库领域客服 Agent。

你只能依据已分配的知识库查询 Tool 回答退款政策、售后规则等文档事实。
回答必须只包含 Tool 返回证据能够直接支持的结论，并简洁说明资料来源。

只回答用户当前问题所需要的最少规则。
即使 Tool 返回了同一文档中的其他段落，也不得主动罗列与当前问题无关的政策。
除非某条额外规则是回答当前问题必不可少的前提，否则不要补充。

当用户只问一个具体事实时，只输出一个简短段落：
“根据 <来源>，<直接答案>。”
给出直接答案后立即结束，不得追加第二段、总结、温馨提示、
“其他规则”“不展开”“与问题无关”等任何元说明。

不得使用模型自身常识补充任何规则、原因、例外、建议、时效或条件。
不得添加支付渠道差异、一般情况等文档未明确写出的内容。
当资料没有明确说明某个条件、例外或结论时，必须明确说“当前资料未说明”。

不得查询订单，不得创建或修改工单，不得编造文档未说明的规则。
"""

TICKET_AGENT_PROMPT = """
你是工单领域客服 Agent。

你只能准备客服工单草稿。
当用户提供客户 ID 和明确问题时，调用已分配的工单准备 Tool。
不得声称工单已经正式创建；正式创建必须经过人工审批流程。
不得查询订单或回答知识库规则。
"""

def create_domain_agent_node(
    model: Any,
    tools: list[BaseTool],
    system_prompt: str,
):
    """创建只绑定指定 Tool 集的异步领域 Agent 节点。"""

    bound_model = model.bind_tools(tools)

    async def domain_agent(
        state: dict[str, Any],
    ) -> dict[str, Any]:
        response = await bound_model.ainvoke(
            [
                SystemMessage(content=system_prompt),
                *state["messages"],
            ]
        )

        return {
            "messages": [response],
        }

    return domain_agent

class DomainAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def create_domain_agent_graph(
    model: Any,
    tools: list[BaseTool],
    system_prompt: str,
):
    """创建一个拥有独立 Tool Loop 的领域 Agent 图。"""

    domain_agent = create_domain_agent_node(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )

    builder = StateGraph(DomainAgentState)

    builder.add_node("agent", domain_agent)
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

    return builder.compile()
