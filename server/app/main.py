"""Точка входу серверної частини: створення застосунку FastAPI."""

from fastapi import APIRouter, FastAPI

from app.api.v1 import (
    admin,
    arming,
    auth,
    device,
    equipment,
    events,
    facilities,
    schedules,
    users,
)
from app.errors import register_error_handlers

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Оберіг — програмна система для безпеки житла",
    description=(
        "REST API серверної частини «Оберіг». Час у запитах і відповідях — "
        "UTC у форматі ISO 8601. Мова повідомлень про помилки обирається за "
        "заголовком Accept-Language (uk, en)."
    ),
    version="0.2.0",
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
    admin,
):
    api.include_router(module.router)


@api.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Повертає стан сервісу для перевірки доступності."""
    return {"status": "ok"}


app.include_router(api)
