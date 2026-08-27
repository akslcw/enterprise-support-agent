from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.observability import HTTP_LOGGER


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


def request_trace_id(request: Request) -> str:
    return getattr(
        request.state,
        "trace_id",
        "unknown",
    )


def error_code_for_status(status_code: int) -> str:
    status_codes = {
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        503: "SERVICE_UNAVAILABLE",
        504: "AGENT_TIMEOUT",
    }

    return status_codes.get(status_code, "HTTP_ERROR")


async def http_exception_handler(
    request: Request,
    error: StarletteHTTPException,
) -> JSONResponse:
    trace_id = request_trace_id(request)

    response = ErrorResponse(
        error=ErrorBody(
            code=error_code_for_status(error.status_code),
            message=str(error.detail),
            trace_id=trace_id,
        )
    )

    return JSONResponse(
        status_code=error.status_code,
        content=response.model_dump(),
    )


async def validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    trace_id = request_trace_id(request)

    response = ErrorResponse(
        error=ErrorBody(
            code="VALIDATION_ERROR",
            message="请求参数不合法。",
            trace_id=trace_id,
        )
    )

    return JSONResponse(
        status_code=422,
        content=response.model_dump(),
    )


async def unhandled_exception_handler(
    request: Request,
    error: Exception,
) -> JSONResponse:
    trace_id = request_trace_id(request)

    HTTP_LOGGER.exception(
        "unhandled_exception",
        extra={
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "error_type": type(error).__name__,
        },
    )

    response = ErrorResponse(
        error=ErrorBody(
            code="INTERNAL_ERROR",
            message="服务内部错误，请稍后重试。",
            trace_id=trace_id,
        )
    )

    return JSONResponse(
        status_code=500,
        content=response.model_dump(),
    )