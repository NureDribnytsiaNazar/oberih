"""Статистика хибних спрацювань (ФМ-6, розділ 2.2.2 Vision & Scope).

FAR(k) = F(k) / N(k) за ковзне вікно W днів, де F — тривоги датчика k,
позначені як хибні, N — усі тривоги цього датчика (крім скасованих).
Якщо N ≥ far_min_alarms і FAR > far_threshold, датчик варто перевірити.
Агрегати обчислюються запитами GROUP BY у PostgreSQL.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import Select, distinct, func, null, select
from sqlalchemy.orm import Session

from app.errors import ForbiddenError
from app.models.devices import Sensor
from app.models.enums import AlarmStatus
from app.models.events import Alarm, AlarmEvent, Event
from app.models.facilities import Facility, FacilitySettings, Zone
from app.models.users import User

CHECK_SENSOR = "check_sensor"
TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class FarRow:
    """Кількість тривог і хибних тривог для однієї групи."""

    key: Any
    name: str | None
    alarms: int
    false_alarms: int

    @property
    def far(self) -> Decimal:
        """Частка хибних тривог із двома знаками після коми."""
        if self.alarms == 0:
            return Decimal(0)
        ratio = Decimal(self.false_alarms) / Decimal(self.alarms)
        return ratio.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FalseAlarmStats:
    """Агрегати за датчиками, зонами та годиною доби."""

    since: datetime
    timezone: str
    sensors: list[FarRow]
    zones: list[FarRow]
    hours: list[FarRow]


def needs_check(row: FarRow, settings: FacilitySettings) -> bool:
    """Рекомендація перевірити датчик: N ≥ мінімуму й FAR строго > порога.

    Порівняння F > поріг × N виконується точно, без округлення частки.
    """
    return row.alarms >= settings.far_min_alarms and Decimal(row.false_alarms) > (
        Decimal(settings.far_threshold) * row.alarms
    )


def false_alarm_stats(
    db: Session, facility: Facility, now: datetime, timezone: str | None = None
) -> FalseAlarmStats:
    """Обчислює агрегати хибних спрацювань об'єкта за вікно far_window_days."""
    _require_tariff_feature(db, facility)
    since = now - timedelta(days=facility.settings.far_window_days)
    tz = timezone or facility.timezone
    return FalseAlarmStats(
        since=since,
        timezone=tz,
        sensors=_rows(db, _by_sensor(facility, since)),
        zones=_rows(db, _by_zone(facility, since)),
        hours=_rows(db, _by_hour(facility, since, tz)),
    )


def _counts() -> tuple[Any, Any]:
    """N — різні тривоги групи, F — різні тривоги з позначкою «хибна»."""
    total = func.count(distinct(Alarm.id))
    false = func.count(distinct(Alarm.id)).filter(Alarm.is_false.is_(True))
    return total, false


def _counted_alarms(facility: Facility, since: datetime) -> Any:
    """Умова: тривоги об'єкта у вікні, крім скасованих (законний вхід)."""
    return (
        (Alarm.facility_id == facility.id)
        & (Alarm.opened_at >= since)
        & (Alarm.status != AlarmStatus.CANCELLED)
    )


def _by_sensor(facility: Facility, since: datetime) -> Select[Any]:
    total, false = _counts()
    return (
        select(Sensor.id, Sensor.name, total, false)
        .select_from(Alarm)
        .join(AlarmEvent, AlarmEvent.alarm_id == Alarm.id)
        .join(Event, Event.id == AlarmEvent.event_id)
        .join(Sensor, Sensor.id == Event.sensor_id)
        .where(_counted_alarms(facility, since))
        .group_by(Sensor.id, Sensor.name)
        .order_by(Sensor.name)
    )


def _by_zone(facility: Facility, since: datetime) -> Select[Any]:
    total, false = _counts()
    return (
        select(Zone.id, Zone.name, total, false)
        .select_from(Alarm)
        .join(Zone, Zone.id == Alarm.zone_id)
        .where(_counted_alarms(facility, since))
        .group_by(Zone.id, Zone.name)
        .order_by(Zone.name)
    )


def _by_hour(facility: Facility, since: datetime, tz: str) -> Select[Any]:
    total, false = _counts()
    # Година доби в місцевому часі: AT TIME ZONE враховує літній час.
    hour = func.extract("hour", func.timezone(tz, Alarm.opened_at)).label("hour")
    return (
        select(hour, null(), total, false)
        .where(_counted_alarms(facility, since))
        .group_by(hour)
        .order_by(hour)
    )


def _rows(db: Session, stmt: Select[Any]) -> list[FarRow]:
    result: Sequence[Any] = db.execute(stmt).all()
    return [
        FarRow(key=key, name=name, alarms=int(total), false_alarms=int(false))
        for key, name, total, false in result
    ]


def _require_tariff_feature(db: Session, facility: Facility) -> None:
    """Статистика хибних спрацювань доступна від стандартного тарифу."""
    owner = db.get_one(User, facility.owner_id)
    if not owner.tariff_plan.false_alarm_stats:
        raise ForbiddenError("tariff_feature")
