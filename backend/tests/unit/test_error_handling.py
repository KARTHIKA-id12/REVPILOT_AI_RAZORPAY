"""Regression test for a real bug found while testing the settings API:
FastAPI/Pydantic v2 includes the raw exception object in
error['ctx']['error'] when a @field_validator raises ValueError with a
custom message. Passing that straight into a JSONResponse crashes the
error handler itself with a TypeError ('ValueError is not JSON
serializable'), turning a clean 422 into an opaque 500 — for EVERY
endpoint with a custom validator, not just one. This is exactly the kind
of infrastructure-level bug that's invisible until a validator's error
path is actually exercised end-to-end over HTTP.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_custom_validator_value_error_returns_clean_422_not_500():
    # Any endpoint with a @field_validator raising ValueError exercises
    # this path — settings/permissions is a convenient real example.
    response = client.put(
        "/api/v1/settings/permissions",
        params={"merchant_id": "00000000-0000-0000-0000-000000000000"},
        json={"permissions": [{"action_code": "NOT_A_REAL_ACTION_CODE", "mode": "ALLOW"}]},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    # The ctx.error field (if present) must be a string, never a raw
    # exception object smuggled through into the JSON payload.
    for err in body["error"]["details"]["errors"]:
        ctx = err.get("ctx")
        if ctx and "error" in ctx:
            assert isinstance(ctx["error"], str)
