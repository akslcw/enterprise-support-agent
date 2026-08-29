from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from redis.asyncio import Redis
from starlette.exceptions import (
    HTTPException as StarletteHTTPException,
)
from starlette.types import ExceptionHandler

from app.api.routers.admin import router as admin_router
from app.api.routers.chat import router as chat_router
from app.api.routers.health import router as health_router
from app.api.routers.tickets import router as tickets_router
from app.cache import OrderStatusCache
from app.cached_tools import create_cached_order_status_tool
from app.error_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from app.llm import create_chat_model
from app.mcp_client import load_mcp_tools
from app.multi_agent import create_multi_agent_graph
from app.observability import (
    TraceIdMiddleware,
    configure_application_logging,
)
from app.runtime import configure_asyncio_for_psycopg
from app.settings import (
    order_status_cache_ttl_seconds,
    postgres_connection_string,
    redis_connection_string,
)

configure_asyncio_for_psycopg()
configure_application_logging()

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

app.add_middleware(TraceIdMiddleware)
app.add_exception_handler(
    StarletteHTTPException,
    cast(
        ExceptionHandler,
        http_exception_handler,
    ),
)
app.add_exception_handler(
    RequestValidationError,
    cast(
        ExceptionHandler,
        validation_error_handler,
    ),
)
app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.include_router(health_router)
app.include_router(chat_router)
app.include_router(tickets_router)
app.include_router(admin_router)