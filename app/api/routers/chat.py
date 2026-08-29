from fastapi import APIRouter, HTTPException, Request, status

from app.api.contracts import ChatRequest
from app.application.chat_service import ChatService
from app.observability import HTTP_LOGGER
from app.reliability import OperationTimeoutError
from app.schemas import (
    ChatCompletedResponse,
    PendingApprovalResponse,
)

router = APIRouter(tags=["chat"])

@router.post(
    "/chat",
    response_model=(
        ChatCompletedResponse
        | PendingApprovalResponse
    ),
)
async def chat(
    body: ChatRequest,
    request: Request,
) -> ChatCompletedResponse | PendingApprovalResponse:
    try:
        return await ChatService(
            request.app.state.graph
        ).run(
            thread_id=body.thread_id,
            message=body.message,
        )
    except OperationTimeoutError:
        HTTP_LOGGER.warning(
            "chat_timeout",
            extra={
                "trace_id": request.state.trace_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Agent 请求超时，请稍后重试。",
        ) from None