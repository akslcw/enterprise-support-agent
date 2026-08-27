import asyncio
import sys


def configure_asyncio_for_psycopg() -> None:
    """在 Windows 上为 Psycopg 异步连接选择兼容的事件循环。"""

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy()
        )