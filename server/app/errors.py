"""Єдиний формат помилок API: {"error": {"code": "...", "message": "..."}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.i18n import resolve_locale, translate

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Помилка предметної області з HTTP-статусом і кодом для клієнта."""

    def __init__(
        self, status_code: int, code: str, details: list[Any] | None = None
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        # Уточнення для клієнта, наприклад поле, у якому знайдено помилку.
        self.details = details


class NotFoundError(AppError):
    """Ресурс не існує або недоступний поточному користувачеві."""

    def __init__(self, code: str = "not_found") -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, code)


class ForbiddenError(AppError):
    """Користувач автентифікований, але не має права на дію."""

    def __init__(self, code: str = "forbidden") -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, code)


class UnauthorizedError(AppError):
    """Потрібна (повторна) автентифікація."""

    def __init__(self, code: str = "not_authenticated") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, code)


class ConflictError(AppError):
    """Дія суперечить поточному стану даних."""

    def __init__(self, code: str = "conflict") -> None:
        super().__init__(status.HTTP_409_CONFLICT, code)


class BadRequestError(AppError):
    """Дані запиту коректні за форматом, але неприйнятні за змістом."""

    def __init__(self, code: str, details: list[Any] | None = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, code, details)


def error_body(
    request: Request, code: str, details: list[Any] | None = None
) -> dict[str, Any]:
    """Формує тіло відповіді з повідомленням мовою клієнта."""
    locale = resolve_locale(
        request.headers.get("accept-language"),
        getattr(request.state, "user_locale", None),
    )
    error: dict[str, Any] = {"code": code, "message": translate(code, locale)}
    if details:
        error["details"] = details
    return {"error": error}


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    headers = None
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        headers = {"WWW-Authenticate": "Bearer"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, exc.code, exc.details),
        headers=headers,
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # Лише місце й тип помилки, без значень полів (там можуть бути паролі).
    details = [
        {"loc": list(err["loc"]), "type": err["type"], "msg": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=error_body(request, "validation_error", details),
    )


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    codes = {
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    }
    code = codes.get(exc.status_code, "internal_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, code),
        headers=getattr(exc, "headers", None),
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body(request, "internal_error"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Підключає обробники, що приводять усі помилки до єдиного формату."""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
