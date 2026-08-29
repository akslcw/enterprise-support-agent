from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.api.contracts import IDENTIFIER_PATTERN
from app.application.thread_admin_service import (
    ThreadAdminService,
    ThreadNotFoundError,
)
from app.session_admin import require_admin_token

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)

def get_thread_admin_service(
    request: Request,
) -> ThreadAdminService:
    """从应用运行时对象创建本次管理请求的 Service。"""

    return ThreadAdminService(
        checkpointer=request.app.state.checkpointer,
        graph=request.app.state.graph,
        order_cache=request.app.state.order_cache,
    )

@router.get("/threads/{thread_id}")
async def get_thread_state(
    request: Request,
    thread_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=IDENTIFIER_PATTERN,
    ),
) -> dict:
    try:
        return await get_thread_admin_service(
            request
        ).get_thread_state(thread_id)
    except ThreadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        ) from None


@router.delete("/threads/{thread_id}")
async def delete_thread_state(
    request: Request,
    thread_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=IDENTIFIER_PATTERN,
    ),
) -> dict:
    try:
        return await get_thread_admin_service(
            request
        ).delete_thread(thread_id)
    except ThreadNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该 thread_id 的会话状态。",
        ) from None


@router.delete("/cache/orders/{order_id}")
async def invalidate_order_status_cache(
    request: Request,
    order_id: str = Path(
        min_length=1,
        max_length=100,
        pattern=IDENTIFIER_PATTERN,
    ),
) -> dict:
    return await get_thread_admin_service(
        request
    ).invalidate_order_status_cache(order_id)