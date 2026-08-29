import os
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量：{name}"
        )

    return value


def postgres_connection_string() -> str:
    user = quote(require_env("POSTGRES_USER"), safe="")
    password = quote(
        require_env("POSTGRES_PASSWORD"),
        safe="",
    )
    host = require_env("POSTGRES_HOST")
    port = require_env("POSTGRES_PORT")
    database = require_env("POSTGRES_DB")

    return (
        f"postgresql://{user}:{password}"
        f"@{host}:{port}/{database}"
    )


def redis_connection_string() -> str:
    host = require_env("REDIS_HOST")
    port = require_env("REDIS_PORT")
    database = require_env("REDIS_DB")

    return f"redis://{host}:{port}/{database}"

def order_status_cache_ttl_seconds() -> int:
    raw_value = os.getenv(
        "ORDER_STATUS_CACHE_TTL_SECONDS",
        "60",
    )

    try:
        ttl_seconds = int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            "ORDER_STATUS_CACHE_TTL_SECONDS 必须是正整数。"
        ) from error

    if ttl_seconds <= 0:
        raise RuntimeError(
            "ORDER_STATUS_CACHE_TTL_SECONDS 必须是正整数。"
        )

    return ttl_seconds

def llm_timeout_seconds() -> int:
    raw_value = os.getenv(
        "LLM_TIMEOUT_SECONDS",
        "30",
    )

    try:
        timeout_seconds = int(raw_value)
    except ValueError as error:
        raise RuntimeError(
            "LLM_TIMEOUT_SECONDS 必须是正整数。"
        ) from error

    if timeout_seconds <= 0:
        raise RuntimeError(
            "LLM_TIMEOUT_SECONDS 必须是正整数。"
        )

    return timeout_seconds

def agent_timeout_seconds() -> float:
    raw_value = os.getenv(
        "AGENT_TIMEOUT_SECONDS",
        "45",
    )

    try:
        timeout_seconds = float(raw_value)
    except ValueError as error:
        raise RuntimeError(
            "AGENT_TIMEOUT_SECONDS 必须是正数。"
        ) from error

    if timeout_seconds <= 0:
        raise RuntimeError(
            "AGENT_TIMEOUT_SECONDS 必须是正数。"
        )

    return timeout_seconds