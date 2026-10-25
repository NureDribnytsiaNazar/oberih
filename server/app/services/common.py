"""Допоміжні функції сервісів."""

import uuid
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError

M = TypeVar("M")


def get_in_facility(
    db: Session, model: type[M], entity_id: uuid.UUID, facility_id: uuid.UUID
) -> M:
    """Повертає запис, що належить об'єкту, або 404 (чужі записи не видно)."""
    entity = db.get(model, entity_id)
    if entity is None or getattr(entity, "facility_id") != facility_id:
        raise NotFoundError()
    return entity


def apply_changes(entity: Any, data: BaseModel) -> None:
    """Переносить у модель лише передані поля (null означає «не змінювати»)."""
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(entity, field, value)


def commit_or_conflict(db: Session, code: str = "conflict") -> None:
    """Фіксує транзакцію; порушення унікальності чи зв'язків дає 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(code)
