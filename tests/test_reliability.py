import asyncio

import pytest

from app.reliability import (
    OperationTimeoutError,
    RetryExhaustedError,
    retry_read_operation,
    run_with_timeout,
)


async def return_value() -> str:
    return "ok"


async def wait_for_test() -> None:
    await asyncio.sleep(1)


def test_run_with_timeout_returns_completed_value() -> None:
    result = asyncio.run(
        run_with_timeout(
            return_value(),
            operation_name="test_operation",
            timeout_seconds=1,
        )
    )

    assert result == "ok"


def test_run_with_timeout_raises_project_timeout_error() -> None:
    with pytest.raises(
        OperationTimeoutError,
        match="slow_operation 超过 0.01 秒时间预算",
    ):
        asyncio.run(
            run_with_timeout(
                wait_for_test(),
                operation_name="slow_operation",
                timeout_seconds=0.01,
            )
        )

def test_retry_read_operation_retries_connection_error() -> None:
    calls: list[int] = []

    async def flaky_operation() -> str:
        calls.append(1)

        if len(calls) < 3:
            raise ConnectionError("temporary failure")

        return "ok"

    result = asyncio.run(
        retry_read_operation(
            flaky_operation,
            operation_name="read_order",
            max_attempts=3,
            initial_delay_seconds=0,
        )
    )

    assert result == "ok"
    assert len(calls) == 3


def test_retry_read_operation_does_not_retry_value_error() -> None:
    calls: list[int] = []

    async def invalid_operation() -> None:
        calls.append(1)
        raise ValueError("invalid payload")

    with pytest.raises(ValueError, match="invalid payload"):
        asyncio.run(
            retry_read_operation(
                invalid_operation,
                operation_name="read_order",
                max_attempts=3,
                initial_delay_seconds=0,
            )
        )

    assert len(calls) == 1


def test_retry_read_operation_reports_exhaustion() -> None:
    calls: list[int] = []

    async def unavailable_operation() -> None:
        calls.append(1)
        raise ConnectionError("service unavailable")

    with pytest.raises(
        RetryExhaustedError,
        match="read_order 在 2 次尝试后仍然失败",
    ):
        asyncio.run(
            retry_read_operation(
                unavailable_operation,
                operation_name="read_order",
                max_attempts=2,
                initial_delay_seconds=0,
            )
        )

    assert len(calls) == 2