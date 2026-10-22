"""Базові класи та допоміжні типи для моделей SQLAlchemy."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Єдина схема іменування обмежень: стабільні імена потрібні для міграцій Alembic.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Спільна основа всіх моделей."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum_cls: type[enum.Enum], name: str | None = None) -> Enum:
    """Створює тип стовпця для перелічення.

    Значення зберігаються як рядки з обмеженням CHECK (без нативного
    типу ENUM у PostgreSQL), що спрощує міграції.
    """
    return Enum(
        enum_cls,
        name=name or enum_cls.__name__.lower(),
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [m.value for m in members],
    )


class UUIDPrimaryKeyMixin:
    """Первинний ключ у вигляді UUID."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Часові мітки створення та оновлення запису (UTC)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
