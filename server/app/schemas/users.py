"""Схеми профілю користувача та тарифів."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.models.enums import Locale, MeasurementSystem
from app.schemas.common import Name, ORMModel


class TariffOut(ORMModel):
    """Тарифний план і його обмеження."""

    id: uuid.UUID
    code: str
    name: str
    price_month: Decimal
    max_facilities: int
    archive_days: int
    email_notifications: bool
    guest_access: bool
    false_alarm_stats: bool
    incident_timeline: bool
    api_access: bool


class UserOut(ORMModel):
    """Профіль користувача."""

    id: uuid.UUID
    email: str
    full_name: str
    locale: Locale
    timezone: str
    measurement_system: MeasurementSystem
    totp_enabled: bool
    is_platform_admin: bool
    tariff_plan: TariffOut
    privacy_consent_at: datetime | None
    created_at: datetime


class UserUpdate(BaseModel):
    """Зміна профілю; передаються лише поля, які треба змінити."""

    full_name: Annotated[Name, Field(max_length=128)] | None = None
    locale: Locale | None = None
    timezone: Annotated[str, Field(max_length=64)] | None = None
    measurement_system: MeasurementSystem | None = None


class DeleteAccountRequest(BaseModel):
    """Видалення облікового запису підтверджується паролем."""

    password: Annotated[str, Field(min_length=1, max_length=128)]


class UserExport(BaseModel):
    """Усі персональні дані користувача (право на доступ, GDPR)."""

    exported_at: datetime
    profile: dict[str, Any]
    memberships: list[dict[str, Any]]
    arming_actions: list[dict[str, Any]]
    alarm_acknowledgements: list[dict[str, Any]]
