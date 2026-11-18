"""Схеми адміністрування платформи."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.models.enums import BackupKind, BackupStatus, CertificateStatus
from app.schemas.common import Confirmation, ORMModel


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
    blocked_at: datetime | None
    anonymized_at: datetime | None
    created_at: datetime


class PlatformAdminUpdate(BaseModel):
    """Надання або зняття прав адміністратора платформи."""

    is_platform_admin: bool


class TariffUpdate(BaseModel):
    """Новий тарифний план користувача."""

    code: Annotated[str, Field(min_length=1, max_length=32)]


class SessionsRevoked(BaseModel):
    """Кількість завершених сесій."""

    revoked: int


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


class ConfirmedAction(BaseModel):
    """Деструктивна дія з повторним підтвердженням паролем або TOTP."""

    confirmation: Confirmation | None = None


class SystemStats(BaseModel):
    """Статистика системи."""

    users: int
    facilities: int
    nodes: int
    events: int
    alarms: int
    archive_bytes: int = Field(description="Розмір подій і тривог разом з індексами")
    database_bytes: int


class PurgeResult(BaseModel):
    """Підсумок очищення застарілих даних."""

    alarms: int
    events: int


class BackupCreate(BaseModel):
    """Створення копії: full — усі дані, settings — лише налаштування."""

    kind: BackupKind = BackupKind.FULL


class BackupOut(ORMModel):
    """Запис про резервну копію."""

    id: uuid.UUID
    kind: BackupKind
    status: BackupStatus
    file_name: str
    size_bytes: int | None
    sha256: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class RestoreResult(BaseModel):
    """Кількість відновлених рядків за таблицями."""

    kind: BackupKind
    rows: dict[str, int]


Days = Annotated[int, Field(ge=1, le=3650)]


class CertificateIssue(BaseModel):
    """Випуск клієнтського сертифіката для вузла."""

    node_id: uuid.UUID
    days: Days = 365
    subject: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class CertificateRenew(BaseModel):
    """Поновлення: новий сертифікат замість старого."""

    days: Days = 365


class CertificateOut(ORMModel):
    """Сертифікат вузла (без приватного ключа)."""

    id: uuid.UUID
    node_id: uuid.UUID | None
    subject: str
    serial_number: str
    status: CertificateStatus
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None
    pem: str


class CertificateIssued(BaseModel):
    """Новий сертифікат і приватний ключ. Ключ показується лише один раз."""

    certificate: CertificateOut
    private_key_pem: str


class CrlOut(BaseModel):
    """Перелік відкликаних серійних номерів."""

    generated_at: datetime
    revoked_serials: list[str]
