import pytest
from fastapi import HTTPException

from app.session_admin import require_admin_token


def test_admin_request_is_unavailable_without_server_token(monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    with pytest.raises(HTTPException) as error:
        require_admin_token(x_admin_token="any-value")

    assert error.value.status_code == 503


def test_admin_request_rejects_missing_or_invalid_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "correct-token")

    with pytest.raises(HTTPException) as missing_error:
        require_admin_token(x_admin_token=None)

    with pytest.raises(HTTPException) as invalid_error:
        require_admin_token(x_admin_token="wrong-token")

    assert missing_error.value.status_code == 403
    assert invalid_error.value.status_code == 403


def test_admin_request_accepts_matching_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "correct-token")

    require_admin_token(x_admin_token="correct-token")
