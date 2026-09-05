import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base application error. Raise this (or a subclass) from services;
    never let raw exceptions/stack traces reach the client."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: dict | None = None):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _envelope(code: str, message: str, request_id: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id, "details": details or {}}}


def _sanitize_validation_errors(errors: list[dict]) -> list[dict]:
    """Pydantic v2 includes the raw exception object in error['ctx']['error']
    for validators that raise ValueError (e.g. `@field_validator`) — that
    object is not JSON-serializable, so passing exc.errors() straight into
    a JSONResponse silently turns a clean 422 into an opaque, misleading
    500 for EVERY custom validator in the app, not just one endpoint. This
    was a real bug found while testing the settings API's validators."""
    sanitized = []
    for error in errors:
        clean = dict(error)
        ctx = clean.get("ctx")
        if isinstance(ctx, dict) and "error" in ctx:
            clean["ctx"] = {**ctx, "error": str(ctx["error"])}
        sanitized.append(clean)
    return sanitized


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, request_id, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "VALIDATION_ERROR", "Request validation failed.", request_id,
                {"errors": _sanitize_validation_errors(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("HTTP_ERROR", str(exc.detail), request_id),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Never leak stack traces / internals to the client.
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "Something went wrong. Please try again.", request_id),
        )
