"""Точка входу серверної частини: створення застосунку FastAPI."""

import asyncio
import contextlib
from collections.abc import AsyncIterator

from fastapi import APIRouter, FastAPI

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
    schedules,
    users,
)
from app.config import settings
from app.errors import register_error_handlers
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
    version="0.3.0",
    lifespan=lifespan,
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
    admin,
    admin_data,
    admin_certificates,
):
    api.include_router(module.router)


@api.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Повертає стан сервісу для перевірки доступності."""
    return {"status": "ok"}


app.include_router(api)
