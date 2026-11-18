"""Схеми статистики хибних спрацювань і тестових сценаріїв."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import AlarmLevel, EventType, FacilityMode
from app.schemas.common import Name, ORMModel
from app.schemas.events import DEVICE_EVENT_TYPES

# --- Статистика хибних спрацювань --------------------------------------------


class FarSensorOut(BaseModel):
    """FAR датчика та рекомендація."""

    sensor_id: uuid.UUID
    sensor_name: str
    alarms: int
    false_alarms: int
    far: Decimal
    recommendation: str | None = Field(description="check_sensor або null")
    recommendation_text: str | None


class FarGroupOut(BaseModel):
    """Агрегат за зоною або за годиною доби."""

    key: str
    name: str | None
    alarms: int
    false_alarms: int
    far: Decimal


class FalseAlarmStatsOut(BaseModel):
    """Статистика хибних спрацювань об'єкта за ковзне вікно."""

    since: datetime
    window_days: int
    timezone: str
    sensors: list[FarSensorOut]
    zones: list[FarGroupOut]
    hours: list[FarGroupOut]


# --- Тестові сценарії --------------------------------------------------------


class ScenarioStepIn(BaseModel):
    """Крок: через offset_ms від початку датчик sensor_id переходить у state."""

    offset_ms: Annotated[int, Field(ge=0, le=24 * 3600 * 1000)]
    sensor_id: uuid.UUID
    state: EventType

    @field_validator("state")
    @classmethod
    def _device_state(cls, value: EventType) -> EventType:
        if value not in DEVICE_EVENT_TYPES:
            raise ValueError("only sensor events can be used in a scenario")
        return value


class ExpectedAlarm(BaseModel):
    """Очікувана тривога: рівень і, за потреби, зона."""

    level: AlarmLevel
    zone_id: uuid.UUID | None = None


class ScenarioCreate(BaseModel):
    """Новий тестовий сценарій."""

    name: Annotated[Name, Field(max_length=128)]
    description: Annotated[str, Field(max_length=2000)] | None = None
    steps: Annotated[list[ScenarioStepIn], Field(min_length=1, max_length=500)]
    expected: Annotated[list[ExpectedAlarm], Field(max_length=100)] = []


class ScenarioUpdate(BaseModel):
    """Зміна сценарію."""

    name: Annotated[Name, Field(max_length=128)] | None = None
    description: Annotated[str, Field(max_length=2000)] | None = None
    steps: (
        Annotated[list[ScenarioStepIn], Field(min_length=1, max_length=500)] | None
    ) = None
    expected: Annotated[list[ExpectedAlarm], Field(max_length=100)] | None = None


class ScenarioOut(ORMModel):
    """Тестовий сценарій."""

    id: uuid.UUID
    facility_id: uuid.UUID
    name: str
    description: str | None
    steps: list[dict[str, Any]]
    expected: list[dict[str, Any]]
    created_at: datetime


class ScenarioRunRequest(BaseModel):
    """Параметри запуску: режим, у якому перебуває об'єкт на початку."""

    mode: FacilityMode = FacilityMode.ARMED_AWAY


class ScenarioRunOut(ORMModel):
    """Результат відтворення сценарію."""

    id: uuid.UUID
    scenario_id: uuid.UUID
    passed: bool
    actual: list[dict[str, Any]]
    mismatches: list[dict[str, Any]]
    started_at: datetime
