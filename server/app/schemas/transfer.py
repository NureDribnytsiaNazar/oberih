"""Документ експорту та імпорту налаштувань об'єкта (формат версії 1).

Зв'язки задаються природними ключами, а не UUID: зона — назвою, вузол —
серійним номером, датчик — номером каналу. Тому документ переноситься
між об'єктами й серверами, а повторний імпорт не створює дублікатів.
"""

from datetime import datetime, time
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.enums import (
    AlarmLevel,
    EventType,
    ScheduleAction,
    SensorType,
    ZoneType,
)
from app.schemas.common import Name
from app.schemas.facilities import FacilitySettingsUpdate

FORMAT_VERSION: Literal[1] = 1
ShortName = Annotated[Name, Field(max_length=128)]


class ZoneDoc(BaseModel):
    """Зона об'єкта."""

    name: ShortName
    zone_type: ZoneType


class SensorDoc(BaseModel):
    """Датчик на каналі вузла; zone — назва зони."""

    channel: Annotated[int, Field(ge=0, le=63)]
    name: ShortName
    sensor_type: SensorType
    zone: ShortName
    is_enabled: bool = True


class NodeDoc(BaseModel):
    """Вузол (без токена пристрою) і його датчики."""

    serial: Annotated[str, Field(min_length=1, max_length=64)]
    name: ShortName
    sensors: list[SensorDoc] = []


class ScheduleDoc(BaseModel):
    """Розклад постановки або зняття."""

    name: ShortName
    action: ScheduleAction
    days_mask: Annotated[int, Field(ge=1, le=127)]
    local_time: time
    enabled: bool = True


class StepDoc(BaseModel):
    """Крок сценарію: датчик задається вузлом і каналом."""

    offset_ms: Annotated[int, Field(ge=0)]
    node_serial: str
    channel: int
    state: EventType


class ExpectedDoc(BaseModel):
    """Очікувана тривога сценарію; zone — назва зони."""

    level: AlarmLevel
    zone: str | None = None


class ScenarioDoc(BaseModel):
    """Тестовий сценарій."""

    name: ShortName
    description: str | None = None
    steps: Annotated[list[StepDoc], Field(min_length=1)]
    expected: list[ExpectedDoc] = []


class SettingsDocument(BaseModel):
    """Налаштування об'єкта для перенесення."""

    format_version: Literal[1] = FORMAT_VERSION
    exported_at: datetime | None = None
    timezone: str | None = None
    settings: FacilitySettingsUpdate = FacilitySettingsUpdate()
    zones: list[ZoneDoc] = []
    nodes: list[NodeDoc] = []
    schedules: list[ScheduleDoc] = []
    scenarios: list[ScenarioDoc] = []


class ImportReport(BaseModel):
    """Що створено, змінено й залишено без змін (за розділами)."""

    dry_run: bool
    created: dict[str, int]
    updated: dict[str, int]
    unchanged: dict[str, int]
