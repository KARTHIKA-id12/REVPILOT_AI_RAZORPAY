import uuid

import pytest

from app.core.config import get_settings
from app.security.auth import create_access_token, get_principal


def test_access_token_round_trip(monkeypatch):
    monkeypatch.setattr(get_settings(), "JWT_SECRET", "unit-test-secret")
    token = create_access_token(uuid.UUID("00000000-0000-0000-0000-000000000001"), expires_minutes=5)
    from fastapi.security import HTTPAuthorizationCredentials

    principal = get_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert principal.user_id == uuid.UUID("00000000-0000-0000-0000-000000000001")


def test_invalid_token_is_rejected(monkeypatch):
    monkeypatch.setattr(get_settings(), "JWT_SECRET", "unit-test-secret")
    from fastapi.security import HTTPAuthorizationCredentials

    from app.core.errors import AppError

    with pytest.raises(AppError) as error:
        get_principal(HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-jwt"))
    assert error.value.code == "INVALID_TOKEN"