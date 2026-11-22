"""Схеми об'єктів, налаштувань, учасників, зон, вузлів, датчиків, розкладів."""

import uuid
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from app.models.enums import (
    FacilityMode,
    FacilityRole,
    NodeStatus,
    ScheduleAction,
    SensorType,
    ZoneType,
)
from app.schemas.common import Email, Name, ORMModel

ShortName = Annotated[Name, Field(max_length=128)]
Weight = Annotated[Decimal, Field(ge=0, le=9.99, decimal_places=2)]

# --- Об'єкти -----------------------------------------------------------------


class FacilityCreate(BaseModel):
    """Новий об'єкт охорони."""

    name: ShortName
    address: Annotated[str, Field(max_length=255)] | None = None
    timezone: Annotated[str, Field(max_length=64)] = "Europe/Kyiv"


class FacilityUpdate(BaseModel):
    """Зміна даних об'єкта."""

    name: ShortName | None = None
    address: Annotated[str, Field(max_length=255)] | None = None
    timezone: Annotated[str, Field(max_length=64)] | None = None


class FacilityOut(ORMModel):
    """Об'єкт охорони та його поточний режим."""

    id: uuid.UUID
    name: str
    address: str | None
    timezone: str
    owner_id: uuid.UUID
    mode: FacilityMode
    mode_changed_at: datetime
    created_at: datetime


class FacilitySettingsOut(ORMModel):
    """Параметри бізнес-логіки об'єкта (розділ 2.2.2 Vision & Scope)."""

    exit_delay_s: int
    entry_delay_s: int
    duplicate_window_s: int
    confirm_window_s: int
    poll_interval_s: int
    missed_polls_limit: int
    weight_reed: Decimal
    weight_pir: Decimal
    weight_tamper: Decimal
    alarm_threshold: Decimal
    confirmed_threshold: Decimal
    far_window_days: int
    far_min_alarms: int
    far_threshold: Decimal


class FacilitySettingsUpdate(BaseModel):
    """Зміна параметрів; передаються лише поля, які треба змінити."""

    exit_delay_s: Annotated[int, Field(ge=0, le=600)] | None = None
    entry_delay_s: Annotated[int, Field(ge=0, le=600)] | None = None
    duplicate_window_s: Annotated[int, Field(ge=1, le=3600)] | None = None
    confirm_window_s: Annotated[int, Field(ge=1, le=3600)] | None = None
    poll_interval_s: Annotated[int, Field(ge=5, le=3600)] | None = None
    missed_polls_limit: Annotated[int, Field(ge=1, le=100)] | None = None
    weight_reed: Weight | None = None
    weight_pir: Weight | None = None
    weight_tamper: Weight | None = None
    alarm_threshold: Weight | None = None
    confirmed_threshold: Weight | None = None
    far_window_days: Annotated[int, Field(ge=1, le=365)] | None = None
    far_min_alarms: Annotated[int, Field(ge=1, le=1000)] | None = None
    far_threshold: Annotated[Decimal, Field(ge=0, le=1, decimal_places=2)] | None = None


# --- Учасники ----------------------------------------------------------------


def _reject_owner(role: FacilityRole | None) -> FacilityRole | None:
    if role == FacilityRole.OWNER:
        raise ValueError("owner role is assigned only when a facility is created")
    return role


class MemberCreate(BaseModel):
    """Додавання наявного користувача до об'єкта."""

    email: Email
    role: FacilityRole
    access_from: AwareDatetime | None = None
    access_until: AwareDatetime | None = None

    _check_role = field_validator("role")(_reject_owner)


class MemberUpdate(BaseModel):
    """Зміна ролі або періоду доступу учасника."""

    role: FacilityRole | None = None
    access_from: AwareDatetime | None = None
    access_until: AwareDatetime | None = None

    _check_role = field_validator("role")(_reject_owner)


class MemberUser(ORMModel):
    """Короткі відомості про користувача-учасника."""

    id: uuid.UUID
    email: str
    full_name: str


class MemberOut(ORMModel):
    """Учасник об'єкта з роллю."""

    id: uuid.UUID
    user: MemberUser
    role: FacilityRole
    access_from: datetime | None
    access_until: datetime | None
    created_at: datetime


# --- Зони --------------------------------------------------------------------


class ZoneCreate(BaseModel):
    """Нова зона об'єкта."""

    name: ShortName
    zone_type: ZoneType


class ZoneUpdate(BaseModel):
    """Зміна зони."""

    name: ShortName | None = None
    zone_type: ZoneType | None = None


class ZoneOut(ORMModel):
    """Зона об'єкта."""

    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    zone_type: ZoneType


# --- Вузли й датчики ---------------------------------------------------------


class NodeCreate(BaseModel):
    """Реєстрація IoT-вузла за серійним номером."""

    name: ShortName
    serial: Annotated[str, Field(min_length=1, max_length=64)]


class NodeUpdate(BaseModel):
    """Зміна назви або налаштувань вузла (ІК-2, ІК-3).

    Зміна налаштувань збільшує config_version і ставить у чергу команду
    set_config. Межі збігаються з межами у прошивці (iot/include/config.h).
    """

    name: ShortName | None = None
    debounce_ms: Annotated[int, Field(ge=10, le=1000)] | None = None
    pir_lockout_s: Annotated[int, Field(ge=0, le=600)] | None = None


class NodeOut(ORMModel):
    """IoT-вузол і його стан зв'язку."""

    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    serial: str
    firmware_version: str | None
    status: NodeStatus
    last_seen_at: datetime | None
    last_seq: int
    commissioned_at: datetime | None
    debounce_ms: int
    pir_lockout_s: int
    config_version: int
    created_at: datetime


class NodeCommissionOut(BaseModel):
    """Токен пристрою й ключ підпису команд. Показуються лише один раз."""

    node_id: uuid.UUID
    device_token: str
    command_key: str = Field(description="Ключ HMAC-SHA256 (64 hex-символи)")
    commissioned_at: datetime


class SensorCreate(BaseModel):
    """Новий датчик на каналі вузла."""

    zone_id: uuid.UUID
    name: ShortName
    sensor_type: SensorType
    channel: Annotated[int, Field(ge=0, le=63)]


class SensorUpdate(BaseModel):
    """Зміна датчика."""

    zone_id: uuid.UUID | None = None
    name: ShortName | None = None
    is_enabled: bool | None = None


class SensorOut(ORMModel):
    """Датчик вузла."""

    id: uuid.UUID
    node_id: uuid.UUID
    zone_id: uuid.UUID
    name: str
    sensor_type: SensorType
    channel: int
    is_enabled: bool


# --- Розклади ----------------------------------------------------------------

DaysMask = Annotated[
    int, Field(ge=1, le=127, description="Біт 0 — понеділок, біт 6 — неділя")
]


class ScheduleCreate(BaseModel):
    """Розклад автоматичної постановки чи зняття (місцевий час об'єкта)."""

    name: ShortName
    action: ScheduleAction
    days_mask: DaysMask
    local_time: time
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    """Зміна розкладу."""

    name: ShortName | None = None
    action: ScheduleAction | None = None
    days_mask: DaysMask | None = None
    local_time: time | None = None
    enabled: bool | None = None


class ScheduleOut(ORMModel):
    """Розклад об'єкта."""

    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    action: ScheduleAction
    days_mask: int
    local_time: time
    enabled: bool
    last_run_at: datetime | None = Field(
        default=None, description="Останній виконаний запуск (UTC)"
    )
