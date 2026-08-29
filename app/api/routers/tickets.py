from fastapi import APIRouter, HTTPException, Request, status

from app.api.contracts import ApprovalRequest
from app.application.ticket_approval_service import (
    PendingApprovalNotFoundError,
    TicketApprovalService,
)
from app.observability import HTTP_LOGGER
from app.reliability import OperationTimeoutError
from app.schemas import TicketApprovalCompletedResponse

router = APIRouter(tags=["tickets"])


async def has_pending_interrupt(
    request: Request,
    thread_id: str,
) -> bool:
    """兼容旧调用方式；实际检查逻辑在 TicketApprovalService。"""

    return await TicketApprovalService(
        request.app.state.graph
    ).has_pending_interrupt(thread_id)


@router.post(
    "/tickets/approval",
    response_model=TicketApprovalCompletedResponse,
)
async def resume_ticket_approval(
    body: ApprovalRequest,
    request: Request,
) -> TicketApprovalCompletedResponse:
    service = TicketApprovalService(
        request.app.state.graph
    )

    try:
        return await service.resume(
            thread_id=body.thread_id,
            approved=body.approved,
        )
    except PendingApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该 thread_id 没有待处理的人工审批。",
        ) from None
    except OperationTimeoutError:
        HTTP_LOGGER.warning(
            "ticket_approval_timeout",
            extra={
                "trace_id": request.state.trace_id,
                "method": request.method,
                "path": request.url.path,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="工单审批处理超时，请稍后确认状态。",
        ) from None