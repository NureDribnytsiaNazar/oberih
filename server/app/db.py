"""Підключення до бази даних і сесії SQLAlchemy."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def make_engine(url: str) -> Engine:
    """Створює рушій БД; час у сесії PostgreSQL завжди в UTC."""
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=utc"},
    )


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Залежність FastAPI: відкриває сесію на час запиту й закриває її."""
    with SessionLocal() as session:
        yield session
