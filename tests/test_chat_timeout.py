import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.contracts import ChatRequest
from app.api.routers.chat import chat


class SlowGraph:
    async def ainvoke(self, *args, **kwargs) -> dict:
        await asyncio.sleep(1)
        return {}


def test_chat_returns_504_when_graph_exceeds_budget(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AGENT_TIMEOUT_SECONDS", "0.01")

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(graph=SlowGraph())
        ),
        state=SimpleNamespace(trace_id="trace-timeout-001"),
        method="POST",
        url=SimpleNamespace(path="/chat"),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            chat(
                ChatRequest(
                    thread_id="timeout-thread",
                    message="订单 1002 到哪里了？",
                ),
                request,
            )
        )

    assert error.value.status_code == 504
    assert error.value.detail == "Agent 请求超时，请稍后重试。"
