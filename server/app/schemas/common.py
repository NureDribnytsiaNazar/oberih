"""Спільні типи схем: сторінка списку, електронна пошта, підтвердження дії."""

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import AuthMethod

T = TypeVar("T")

# Достатня для API перевірка формату; підтвердження адреси листом — поза ЛБ2.
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ORMModel(BaseModel):
    """Схема відповіді, що будується з об'єкта моделі SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    """Сторінка списку з загальною кількістю записів."""

    items: list[T]
    total: int
    limit: int
    offset: int


class Confirmation(BaseModel):
    """Повторне підтвердження чутливої дії паролем або кодом TOTP."""

    method: AuthMethod = Field(
        description="password або totp; pin і biometric — у мобільному клієнті"
    )
    value: str = Field(min_length=1, max_length=128)
