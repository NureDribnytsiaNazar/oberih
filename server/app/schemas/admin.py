"""Схеми адміністрування платформи."""

import uuid
from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class AdminTariffRef(ORMModel):
    """Тариф користувача (скорочено)."""

    code: str
    name: str


class AdminUserOut(ORMModel):
    """Обліковий запис для адміністратора."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_platform_admin: bool
    totp_enabled: bool
    tariff_plan: AdminTariffRef
    anonymized_at: datetime | None
    created_at: datetime


class AuditLogOut(ORMModel):
    """Запис журналу аудиту."""

    id: int
    user_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    ip_address: str | None
    details: dict[str, Any] | None
    created_at: datetime
