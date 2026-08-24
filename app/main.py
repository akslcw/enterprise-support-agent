from fastapi import FastAPI
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage

from app.agent import graph


app = FastAPI(
    title="Enterprise Support Agent",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(body: ChatRequest) -> dict[str, str]:
    result = graph.invoke(
        {
            "messages": [
                HumanMessage(content=body.message),
            ]
        }
    )

    final_message = result["messages"][-1]

    return {"answer": str(final_message.content)}