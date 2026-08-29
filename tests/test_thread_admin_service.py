import asyncio
from types import SimpleNamespace

import pytest

from app.application.thread_admin_service import (
    ThreadAdminService,
    ThreadNotFoundError,
)


class FakeCheckpointer:
    def __init__(self, checkpoint: object | None) -> None:
        self.checkpoint = checkpoint
        self.get_calls: list[dict] = []
        self.deleted_threads: list[str] = []

    async def aget_tuple(self, config: dict):
        self.get_calls.append(config)
        return self.checkpoint

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted_threads.append(thread_id)


class FakeGraph:
    def __init__(self, messages: list) -> None:
        self.messages = messages
        self.state_calls: list[dict] = []

    async def aget_state(self, config: dict):
        self.state_calls.append(config)
        return SimpleNamespace(
            values={
                "messages": self.messages,
            }
        )


class FakeOrderCache:
    def __init__(self) -> None:
        self.invalidated_orders: list[str] = []

    async def invalidate(self, order_id: str) -> None:
        self.invalidated_orders.append(order_id)


def create_service(
    checkpoint: object | None = object(),
    messages: list | None = None,
) -> tuple[
    ThreadAdminService,
    FakeCheckpointer,
    FakeGraph,
    FakeOrderCache,
]:
    checkpointer = FakeCheckpointer(checkpoint)
    graph = FakeGraph(messages or [])
    order_cache = FakeOrderCache()

    return (
        ThreadAdminService(
            checkpointer=checkpointer,
            graph=graph,
            order_cache=order_cache,
        ),
        checkpointer,
        graph,
        order_cache,
    )


def test_service_returns_thread_messages() -> None:
    messages = [
        SimpleNamespace(
            type="human",
            content="订单 1002 到哪里了？",
        ),
        SimpleNamespace(
            type="ai",
            content="订单正在运输中。",
        ),
    ]
    service, checkpointer, graph, _ = create_service(
        messages=messages
    )

    result = asyncio.run(
        service.get_thread_state("admin-thread-001")
    )

    assert result == {
        "thread_id": "admin-thread-001",
        "message_count": 2,
        "messages": [
            {
                "type": "human",
                "content": "订单 1002 到哪里了？",
            },
            {
                "type": "ai",
                "content": "订单正在运输中。",
            },
        ],
    }
    assert checkpointer.get_calls == [
        {
            "configurable": {
                "thread_id": "admin-thread-001",
            }
        }
    ]
    assert graph.state_calls == checkpointer.get_calls


def test_service_rejects_unknown_thread() -> None:
    service, _, _, _ = create_service(checkpoint=None)

    with pytest.raises(ThreadNotFoundError):
        asyncio.run(
            service.get_thread_state("missing-thread")
        )


def test_service_deletes_existing_thread() -> None:
    service, checkpointer, _, _ = create_service()

    result = asyncio.run(
        service.delete_thread("delete-thread-001")
    )

    assert result == {
        "thread_id": "delete-thread-001",
        "deleted": True,
    }
    assert checkpointer.deleted_threads == [
        "delete-thread-001"
    ]


def test_service_invalidates_order_cache() -> None:
    service, _, _, order_cache = create_service()

    result = asyncio.run(
        service.invalidate_order_status_cache("1002")
    )

    assert result == {
        "order_id": "1002",
        "invalidated": True,
    }
    assert order_cache.invalidated_orders == ["1002"]