from typing import Literal
from langchain_core.tools import tool

from app.schemas import CreateTicketInput
from app.services.tickets import prepare_create_ticket as prepare_ticket
from app.rag.retriever import search_knowledge as retrieve_knowledge

@tool
def prepare_create_ticket(
    customer_id: str,
    title: str,
    priority: Literal["low", "normal", "high"] = "normal",
) -> dict:
    """准备创建客服工单。该操作不会真正创建工单，只会返回等待用户确认的结果。"""
    command = CreateTicketInput(
        customer_id=customer_id,
        title=title,
        priority=priority,
    )

    result = prepare_ticket(command)

    return result.model_dump()

@tool
def get_order_status(order_id: str) -> str:
    """根据订单编号查询当前订单状态。仅在用户询问指定订单进度时使用。"""
    mock_orders = {
        "1001": "已付款，等待发货",
        "1002": "运输中，预计明天送达",
        "1003": "已完成",
        "1004": "已取消",
    }

    return mock_orders.get(order_id, "未找到该订单")

@tool
def search_knowledge(question: str) -> str:
    """查询企业客服知识库，用于回答退款政策、售后规则等文档中已有依据的问题。

    只有在需要根据知识库文档回答问题时才调用。
    参数 question 应保留用户问题中的关键业务含义。
    """

    matches = retrieve_knowledge(question, limit=2)

    if not matches:
        return "知识库中没有找到相关资料。"

    evidence_blocks = []

    for index, match in enumerate(matches, start=1):
        evidence_blocks.append(
            f"证据 {index}\n"
            f"来源：{match['source']}\n"
            f"内容：{match['text']}"
        )

    return "\n\n".join(evidence_blocks)