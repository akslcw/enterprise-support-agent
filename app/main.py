from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field

from app.agent import create_graph
from app.mcp_client import load_mcp_tools
from app.session_admin import require_admin_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_tools = await load_mcp_tools()
    checkpointer = InMemorySaver()

    app.state.checkpointer = checkpointer
    app.state.graph = create_graph(
        mcp_tools,
        checkpointer,
    )

    yield


app = FastAPI(
    title="Enterprise Support Agent",
    version="0.1.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
async def chat(body: ChatRequest, request: Request) -> dict[str, str]:
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

    final_message = result["messages"][-1]

    return {"answer": str(final_message.content)}


def thread_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


@app.get(
    "/admin/threads/{thread_id}",
    dependencies=[Depends(require_admin_token)],
)
def get_thread_state(thread_id: str, request: Request) -> dict:
    config = thread_config(thread_id)

    checkpoint = request.app.state.checkpointer.get_tuple(config)

    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        )

    state = request.app.state.graph.get_state(config)
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
def delete_thread_state(thread_id: str, request: Request) -> dict:
    config = thread_config(thread_id)

    checkpoint = request.app.state.checkpointer.get_tuple(config)

    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        )

    request.app.state.checkpointer.delete_thread(thread_id)

    return {
        "thread_id": thread_id,
        "deleted": True,
    }
