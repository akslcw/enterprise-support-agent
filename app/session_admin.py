import hmac
import os

from fastapi import Header, HTTPException, status


def require_admin_token(
    x_admin_token: str | None = Header(default=None),
) -> None:
    """验证会话管理接口的管理员令牌。"""

    expected_token = os.getenv("ADMIN_API_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="会话管理功能未配置 ADMIN_API_TOKEN。",
        )

    if not x_admin_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缺少 X-Admin-Token 请求头。",
        )

    if not hmac.compare_digest(x_admin_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理员令牌无效。",
        )