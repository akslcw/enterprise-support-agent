import json
import logging
import re

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


TRACE_ID_HEADER = "X-Trace-ID"
HTTP_LOGGER = logging.getLogger("enterprise_support.http")
TRACE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)

def create_trace_id() -> str:
    """生成服务端 Trace ID。"""

    return uuid4().hex


def is_valid_trace_id(trace_id: str) -> bool:
    """确认客户端 Trace ID 可安全写入响应头和日志。"""

    return bool(
        TRACE_ID_PATTERN.fullmatch(trace_id)
    )


def resolve_trace_id(
    requested_trace_id: str | None,
) -> str:
    """保留合法客户端 Trace ID；其余情况由服务端生成。"""

    if (
        requested_trace_id is not None
        and is_valid_trace_id(requested_trace_id)
    ):
        return requested_trace_id

    return create_trace_id()


class JsonLogFormatter(logging.Formatter):
    """将应用日志格式化为单行 JSON。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }

        for field_name in (
            "trace_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "error_type",
        ):
            value = getattr(record, field_name, None)

            if value is not None:
                payload[field_name] = value

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            ensure_ascii=False,
        )


def configure_application_logging() -> None:
    """为 enterprise_support 日志树配置一次 JSON 控制台输出。"""

    application_logger = logging.getLogger(
        "enterprise_support"
    )
    application_logger.setLevel(logging.INFO)
    application_logger.propagate = False

    already_configured = any(
        getattr(handler, "_enterprise_support_handler", False)
        for handler in application_logger.handlers
    )

    if already_configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._enterprise_support_handler = True

    application_logger.addHandler(handler)


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求创建或透传 Trace ID，并记录结构化请求日志。"""

    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        trace_id = resolve_trace_id(
            request.headers.get(TRACE_ID_HEADER)
        )
        request.state.trace_id = trace_id
        started_at = perf_counter()

        try:
            response = await call_next(request)
        except Exception as error:
            HTTP_LOGGER.exception(
                "http_request_failed",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(
                        (perf_counter() - started_at) * 1000,
                        2,
                    ),
                    "error_type": type(error).__name__,
                },
            )
            raise

        duration_ms = round(
            (perf_counter() - started_at) * 1000,
            2,
        )

        response.headers[TRACE_ID_HEADER] = trace_id

        HTTP_LOGGER.info(
            "http_request_completed",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response