"""Точка входу серверної частини: створення застосунку FastAPI."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import (
    admin,
    admin_certificates,
    admin_data,
    analytics,
    arming,
    auth,
    device,
    equipment,
    events,
    facilities,
    meta,
    schedules,
    transfer,
    users,
)
from app.config import settings
from app.deps import DbSession
from app.errors import AppError, register_error_handlers
from app.responses import UTF8JSONResponse
from app.worker import run_worker

API_PREFIX = "/api/v1"


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Запускає фоновий виконавець таймерів на час роботи застосунку."""
    if not settings.worker_enabled:
        yield
        return
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(stop))
    try:
        yield
    finally:
        stop.set()
        await task


app = FastAPI(
    title="Оберіг — програмна система для безпеки житла",
    description=(
        "REST API серверної частини «Оберіг». Час у запитах і відповідях — "
        "UTC у форматі ISO 8601. Мова повідомлень про помилки обирається за "
        "заголовком Accept-Language (uk, en)."
    ),
    version="0.5.0",
    lifespan=lifespan,
    default_response_class=UTF8JSONResponse,
)
register_error_handlers(app)

api = APIRouter(prefix=API_PREFIX)
for module in (
    auth,
    users,
    facilities,
    equipment,
    schedules,
    arming,
    device,
    events,
    analytics,
    transfer,
    admin,
    admin_data,
    admin_certificates,
    meta,
):
    api.include_router(module.router)


@api.get("/health", tags=["service"])
def health(db: DbSession) -> dict[str, str]:
    """Стан сервісу й підключення до БД (HEALTHCHECK контейнера, smoke-тест)."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise AppError(503, "service_unavailable") from exc
    return {"status": "ok", "database": "ok"}


app.include_router(api)
