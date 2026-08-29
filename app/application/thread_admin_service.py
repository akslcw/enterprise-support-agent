from typing import Any


class ThreadNotFoundError(Exception):
    """指定 thread_id 没有已保存的会话状态。"""


def thread_config(thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
        }
    }


class ThreadAdminService:
    """处理管理员的线程查看、删除和订单缓存失效用例。"""

    def __init__(
        self,
        checkpointer: Any,
        graph: Any,
        order_cache: Any,
    ) -> None:
        self._checkpointer = checkpointer
        self._graph = graph
        self._order_cache = order_cache

    async def get_thread_state(
        self,
        thread_id: str,
    ) -> dict:
        config = thread_config(thread_id)

        checkpoint = await self._checkpointer.aget_tuple(
            config
        )

        if checkpoint is None:
            raise ThreadNotFoundError

        state = await self._graph.aget_state(config)
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

    async def delete_thread(
        self,
        thread_id: str,
    ) -> dict:
        config = thread_config(thread_id)

        checkpoint = await self._checkpointer.aget_tuple(
            config
        )

        if checkpoint is None:
            raise ThreadNotFoundError

        await self._checkpointer.adelete_thread(thread_id)

        return {
            "thread_id": thread_id,
            "deleted": True,
        }

    async def invalidate_order_status_cache(
        self,
        order_id: str,
    ) -> dict:
        await self._order_cache.invalidate(order_id)

        return {
            "order_id": order_id,
            "invalidated": True,
        }