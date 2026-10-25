"""Exception handlers that turn every error into one JSON shape:

    {"error": {"code": "not_found", "message": "...", "details": [...optional...]}}

Stack traces and internal messages are logged, never returned to the client.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError

logger = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "permission_denied",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    429: "rate_limited",
}


def error_response(
    status_code: int, code: str, message: str, details: list | dict | None = None, headers: dict | None = None
) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    log = logger.warning if exc.status_code >= 500 else logger.info
    cause = exc.__cause__
    log("Request failed", extra={"error_code": exc.code, "cause": type(cause).__name__ if cause else None})
    headers = None
    if exc.details and "retry_after_seconds" in exc.details:
        headers = {"Retry-After": str(exc.details["retry_after_seconds"])}
    return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {"field": ".".join(str(part) for part in error["loc"] if part != "body"), "message": error["msg"]}
        for error in exc.errors()
    ]
    return error_response(422, "validation_error", "The request data is invalid.", details)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return error_response(exc.status_code, _HTTP_CODES.get(exc.status_code, "http_error"), message, headers=exc.headers)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return error_response(500, AppError.code, AppError.default_message)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
