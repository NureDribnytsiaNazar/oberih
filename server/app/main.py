"""Точка входу серверної частини: створення застосунку FastAPI."""

from fastapi import FastAPI

app = FastAPI(
    title="Оберіг — програмна система для безпеки житла",
    version="0.1.0",
)


@app.get("/health", tags=["service"])
def health() -> dict[str, str]:
    """Повертає стан сервісу для перевірки доступності."""
    return {"status": "ok"}
