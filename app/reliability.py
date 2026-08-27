import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


ResultType = TypeVar("ResultType")


class OperationTimeoutError(RuntimeError):
    """受控操作超出时间预算。"""

    def __init__(
        self,
        operation_name: str,
        timeout_seconds: float,
    ) -> None:
        super().__init__(
            f"{operation_name} 超过 {timeout_seconds} 秒时间预算。"
        )
        self.operation_name = operation_name
        self.timeout_seconds = timeout_seconds


async def run_with_timeout(
    operation: Awaitable[ResultType],
    *,
    operation_name: str,
    timeout_seconds: float,
) -> ResultType:
    """运行协程；超时后转换为项目自己的明确异常。"""

    try:
        return await asyncio.wait_for(
            operation,
            timeout=timeout_seconds,
        )
    except TimeoutError as error:
        raise OperationTimeoutError(
            operation_name,
            timeout_seconds,
        ) from error

class RetryExhaustedError(RuntimeError):
    """可重试的只读操作在最大尝试次数后仍然失败。"""

    def __init__(
        self,
        operation_name: str,
        max_attempts: int,
    ) -> None:
        super().__init__(
            f"{operation_name} 在 {max_attempts} 次尝试后仍然失败。"
        )
        self.operation_name = operation_name
        self.max_attempts = max_attempts


async def retry_read_operation(
    operation: Callable[[], Awaitable[ResultType]],
    *,
    operation_name: str,
    max_attempts: int = 3,
    initial_delay_seconds: float = 0.1,
) -> ResultType:
    """只为幂等读取操作执行有限次数的指数退避重试。"""

    if max_attempts < 1:
        raise ValueError("max_attempts 至少为 1。")

    for attempt in range(1, max_attempts + 1):
        try:
            return await operation()
        except (TimeoutError, OSError) as error:
            if attempt == max_attempts:
                raise RetryExhaustedError(
                    operation_name,
                    max_attempts,
                ) from error

            delay_seconds = initial_delay_seconds * (
                2 ** (attempt - 1)
            )

            await asyncio.sleep(delay_seconds)

    raise RuntimeError("不应到达这里。")