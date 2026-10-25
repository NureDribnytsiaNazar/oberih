"""Запис дій у журнал аудиту (лише додавання, СЧ-10)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.admin import AuditLogEntry


def record(
    db: Session,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str | None = None,
    entity_id: object | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Додає запис аудиту до поточної транзакції (без паролів і токенів)."""
    db.add(
        AuditLogEntry(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
        )
    )
