import pytest
from app.settings import (
    order_status_cache_ttl_seconds,
    postgres_connection_string,
    redis_connection_string,
)

def configure_database_env(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "enterprise app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pass@word")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "enterprise_support")
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "0")


def test_postgres_connection_string_encodes_credentials(
    monkeypatch,
) -> None:
    configure_database_env(monkeypatch)

    assert postgres_connection_string() == (
        "postgresql://enterprise%20app:pass%40word"
        "@127.0.0.1:5432/enterprise_support"
    )


def test_redis_connection_string(monkeypatch) -> None:
    configure_database_env(monkeypatch)

    assert redis_connection_string() == (
        "redis://127.0.0.1:6379/0"
    )

def test_order_status_cache_ttl_seconds_uses_default(
    monkeypatch,
) -> None:
    monkeypatch.delenv(
        "ORDER_STATUS_CACHE_TTL_SECONDS",
        raising=False,
    )

    assert order_status_cache_ttl_seconds() == 60


def test_order_status_cache_ttl_seconds_reads_valid_value(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ORDER_STATUS_CACHE_TTL_SECONDS",
        "120",
    )

    assert order_status_cache_ttl_seconds() == 120


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_order_status_cache_ttl_seconds_rejects_invalid_value(
    monkeypatch,
    value,
) -> None:
    monkeypatch.setenv(
        "ORDER_STATUS_CACHE_TTL_SECONDS",
        value,
    )

    with pytest.raises(
        RuntimeError,
        match="必须是正整数",
    ):
        order_status_cache_ttl_seconds()