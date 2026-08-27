from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.llm import create_chat_model
from app.multi_agent import create_multi_agent_graph
from app.mcp_client import load_mcp_tools
from app.session_admin import require_admin_token
from app.runtime import configure_asyncio_for_psycopg
from app.cache import OrderStatusCache
from app.cached_tools import create_cached_order_status_tool
from app.settings import (
    order_status_cache_ttl_seconds,
    postgres_connection_string,
    redis_connection_string,
)

configure_asyncio_for_psycopg()

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(
        redis_connection_string(),
        decode_responses=True,
    )

    try:
        await redis.ping()

        mcp_tools = await load_mcp_tools()
        order_cache = OrderStatusCache(
            redis,
            ttl_seconds=order_status_cache_ttl_seconds(),
        )

        cached_mcp_tools = [
            (
                create_cached_order_status_tool(
                    tool,
                    order_cache,
                )
                if tool.name == "order_get_status"
                else tool
            )
            for tool in mcp_tools
        ]

        async with AsyncPostgresSaver.from_conn_string(
            postgres_connection_string()
        ) as checkpointer:
            await checkpointer.setup()

            app.state.checkpointer = checkpointer
            app.state.redis = redis
            app.state.order_cache = order_cache
            app.state.graph = create_multi_agent_graph(
                mcp_tools=cached_mcp_tools,
                checkpointer=checkpointer,
                supervisor_model=create_chat_model(
                    thinking="disabled"
                ),
                order_model=create_chat_model(),
                knowledge_model=create_chat_model(),
                ticket_model=create_chat_model(),
            )

            yield
    finally:
        await redis.aclose()

app = FastAPI(
    title="Enterprise Support Agent",
    version="0.1.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)

class ApprovalRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    approved: bool

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict[str, Any]:
    result = await request.app.state.graph.ainvoke(
        {
            "messages": [
                HumanMessage(content=body.message),
            ]
        },
        config={
            "configurable": {
                "thread_id": body.thread_id,
            }
        },
    )

    approval = get_interrupt_payload(result)

    if approval is not None:
        return {
            "status": "pending_approval",
            "thread_id": body.thread_id,
            "approval": approval,
        }

    final_message = result["messages"][-1]

    return {
        "status": "completed",
        "answer": str(final_message.content),
    }

def get_interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    """提取 Graph 暂停时需要交给人工审批者的内容。"""

    interrupts = result.get("__interrupt__", [])

    if not interrupts:
        return None

    payload = interrupts[0].value

    if not isinstance(payload, dict):
        return None

    return payload

def thread_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }

async def has_pending_interrupt(
    request: Request,
    thread_id: str,
) -> bool:
    """判断指定会话是否存在尚未恢复的人工审批。"""

    state = await request.app.state.graph.aget_state(
        thread_config(thread_id)
    )

    return any(task.interrupts for task in state.tasks)


@app.post("/tickets/approval")
async def resume_ticket_approval(
    body: ApprovalRequest,
    request: Request,
) -> dict[str, Any]:
    if not await has_pending_interrupt(request, body.thread_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 thread_id 没有待处理的人工审批。",
        )

    result = await request.app.state.graph.ainvoke(
        Command(resume={"approved": body.approved}),
        config=thread_config(body.thread_id),
    )

    final_message = result["messages"][-1]

    return {
        "status": "completed",
        "thread_id": body.thread_id,
        "approved": body.approved,
        "answer": str(final_message.content),
    }

@app.get(
    "/admin/threads/{thread_id}",
    dependencies=[Depends(require_admin_token)],
)
async def get_thread_state(
    thread_id: str,
    request: Request,
) -> dict:
    config = thread_config(thread_id)

    checkpoint = await request.app.state.checkpointer.aget_tuple(
        config
    )

    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        )

    state = await request.app.state.graph.aget_state(config)
    messages = state.values.get("messages", [])

    return {
        "thread_id": thread_id,
        "message_count": len(messages),
        "messages": [
            {
                "type": message.type,
                "content": str(message.content),
            }
            for message in messages
        ],
    }


@app.delete(
    "/admin/threads/{thread_id}",
    dependencies=[Depends(require_admin_token)],
)
async def delete_thread_state(
    thread_id: str,
    request: Request,
) -> dict:
    config = thread_config(thread_id)

    checkpoint = await request.app.state.checkpointer.aget_tuple(
        config
    )

    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        )

    await request.app.state.checkpointer.adelete_thread(thread_id)

    return {
        "thread_id": thread_id,
        "deleted": True,
    }

@app.delete(
    "/admin/cache/orders/{order_id}",
    dependencies=[Depends(require_admin_token)],
)
async def invalidate_order_status_cache(
    order_id: str,
    request: Request,
) -> dict:
    await request.app.state.order_cache.invalidate(order_id)

    return {
        "order_id": order_id,
        "invalidated": True,
    }