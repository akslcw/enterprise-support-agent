import json
from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt

from app.llm import create_chat_model
from app.schemas import TicketDraft
from app.services.tickets import create_ticket_from_draft
from app.tools import prepare_create_ticket, search_knowledge


SYSTEM_PROMPT = """
你是企业客服助手，只处理订单、工单、退款政策和已接入知识库的企业支持问题。
不得使用模型自身常识回答天气、新闻、医疗、法律、投资等超出企业客服范围的问题。
对超出范围的问题，应简洁说明“当前服务不支持该问题”。

当用户询问指定订单的状态或进度时，调用 order_get_status。
当用户要求创建工单，并提供客户 ID 与明确的问题描述时，调用 prepare_create_ticket。
问题描述可以直接作为工单标题；如果用户已经表达了具体问题，不要再次追问工单标题。
不要编造订单状态、客户信息或工单结果。

用户询问退款政策、售后规则、产品规则或知识库文档中的事实时，必须先调用 search_knowledge。
回答知识库问题时，只能依据 Tool 返回的证据，不得编造未检索到的规则。
当 search_knowledge 返回“知识库中没有找到相关资料”时，不得猜测或补充答案。
回答中应简洁说明资料来源，例如“根据 refund-policy.md”。
每一条知识库规则都必须独立理解；不得把不同段落中的条件自行组合，推导出文档未明确写出的新规则。
当用户问题包含文档没有明确说明的条件、例外或结论时，要明确说“当前资料未说明”，不要猜测。
"""


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    pending_ticket: dict[str, Any] | None
    approval_decision: bool | None

def parse_tool_result(message: ToolMessage) -> dict[str, Any] | None:
    """把 ToolMessage 中的 JSON 结果安全地解析为字典。"""

    if not isinstance(message.content, str):
        return None

    try:
        result = json.loads(message.content)
    except json.JSONDecodeError:
        return None

    if not isinstance(result, dict):
        return None

    return result


def capture_ticket_draft(state: AgentState) -> dict:
    """识别成功创建的工单草稿，写入 pending_ticket。"""

    if not state["messages"]:
        return {}

    last_message = state["messages"][-1]

    if not isinstance(last_message, ToolMessage):
        return {}

    if last_message.name != "prepare_create_ticket":
        return {}

    result = parse_tool_result(last_message)

    if result is None or result.get("ok") is not True:
        return {}

    data = result.get("data")

    if not isinstance(data, dict):
        return {}

    draft = TicketDraft.model_validate(data)

    if draft.status != "pending_confirmation":
        return {}

    return {"pending_ticket": draft.model_dump()}

def route_after_tools(state: AgentState) -> str:
    """决定 Tool 执行后下一步去哪里。"""

    if state.get("pending_ticket") is not None:
        return "request_ticket_approval"

    return "agent"
    
def request_ticket_approval(state: AgentState) -> dict:
    """暂停 Graph，等待人工确认后才正式创建工单。"""

    raw_draft = state.get("pending_ticket")

    if raw_draft is None:
        raise ValueError("审批节点缺少待确认工单草稿")

    draft = TicketDraft.model_validate(raw_draft)

    decision = interrupt(
        {
            "type": "ticket_approval",
            "message": "请确认是否正式创建工单。",
            "draft": draft.model_dump(),
        }
    )

    approved = isinstance(decision, dict) and decision.get("approved") is True

    if not approved:
        return {
            "pending_ticket": None,
            "approval_decision": False,
            "messages": [
                AIMessage(
                    content="工单草稿已取消，未执行正式创建。"
                )
            ],
        }

    result = create_ticket_from_draft(draft)

    if result.ok:
        created_ticket_id = (
            result.data["ticket_id"]
            if result.data is not None
            else "未知"
        )
        content = f"工单已正式创建，工单编号为 {created_ticket_id}。"
    else:
        content = f"工单未能创建：{result.message}。"

    return {
        "pending_ticket": None,
        "approval_decision": True,
        "messages": [AIMessage(content=content)],
    }


def create_graph(
    mcp_tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
):
    """使用启动时发现的 MCP Tools 创建异步 LangGraph。"""

    tools = [
        prepare_create_ticket,
        search_knowledge,
        *mcp_tools,
    ]

    model = create_chat_model().bind_tools(tools)

    async def call_model(state: AgentState) -> dict:
        system_message = SystemMessage(content=SYSTEM_PROMPT)

        response = await model.ainvoke(
            [system_message, *state["messages"]]
        )

        return {"messages": [response]}

    builder = StateGraph(AgentState)

    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))
    builder.add_node("capture_ticket_draft", capture_ticket_draft)
    builder.add_node("request_ticket_approval", request_ticket_approval)

    builder.add_edge(START, "agent")

    builder.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END,
        },
    )

    builder.add_edge("tools", "capture_ticket_draft")

    builder.add_conditional_edges(
        "capture_ticket_draft",
        route_after_tools,
        {
            "request_ticket_approval": "request_ticket_approval",
            "agent": "agent",
        },
    )

    builder.add_edge("request_ticket_approval", END)

    return builder.compile(checkpointer=checkpointer)
