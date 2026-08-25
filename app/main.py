from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from app.agent import create_graph
from app.mcp_client import load_mcp_tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    mcp_tools = await load_mcp_tools()

    app.state.graph = create_graph(mcp_tools)

    yield


app = FastAPI(
    title="Enterprise Support Agent",
    version="0.1.0",
    lifespan=lifespan,
)


class ChatRequest(BaseModel):
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
        }
    )

    final_message = result["messages"][-1]

    return {"answer": str(final_message.content)}