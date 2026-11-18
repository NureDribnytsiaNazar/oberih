"""Чисте ядро конвеєра обробки подій (розділ 2.2.2 Vision & Scope).

Функції приймають дані й параметри об'єкта та повертають рішення, не
звертаючись до БД. Те саме ядро використовують приймання подій від вузлів
(processor.py) і відтворення тестових сценаріїв (simulator.py).
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.models.enums import AlarmLevel, EventType, FacilityMode, SensorType, ZoneType
from app.models.facilities import FacilitySettings
from app.services.state_machine import ARMED_MODES, ModeTrigger

# Події, що означають спрацювання датчика; решта (закриття, відновлення
# корпусу) лише архівуються.
TRIGGER_EVENTS = frozenset({EventType.OPENED, EventType.MOTION, EventType.TAMPER})
# Режими, у яких датчики периметра й внутрішніх зон не породжують тривог.
UNGUARDED_MODES = frozenset({FacilityMode.DISARMED, FacilityMode.EXIT_DELAY})
LEVEL_ORDER = {AlarmLevel.WARNING: 0, AlarmLevel.ALARM: 1, AlarmLevel.CONFIRMED: 2}


@dataclass(frozen=True)
class RuleSettings:
    """Параметри правил об'єкта (значення з facility_settings)."""

    duplicate_window: timedelta
    confirm_window: timedelta
    exit_delay_s: int
    entry_delay_s: int
    weights: Mapping[SensorType, Decimal]
    alarm_threshold: Decimal
    confirmed_threshold: Decimal

    @classmethod
    def from_model(cls, settings: FacilitySettings) -> "RuleSettings":
        """Будує параметри з налаштувань об'єкта в БД."""
        return cls(
            duplicate_window=timedelta(seconds=settings.duplicate_window_s),
            confirm_window=timedelta(seconds=settings.confirm_window_s),
            exit_delay_s=settings.exit_delay_s,
            entry_delay_s=settings.entry_delay_s,
            weights={
                SensorType.REED: Decimal(settings.weight_reed),
                SensorType.PIR: Decimal(settings.weight_pir),
                SensorType.TAMPER: Decimal(settings.weight_tamper),
            },
            alarm_threshold=Decimal(settings.alarm_threshold),
            confirmed_threshold=Decimal(settings.confirmed_threshold),
        )


@dataclass(frozen=True)
class SensorRef:
    """Датчик і зона, до якої він належить."""

    sensor_id: uuid.UUID
    sensor_type: SensorType
    zone_id: uuid.UUID
    zone_type: ZoneType


@dataclass(frozen=True)
class Reading:
    """Подія датчика: що сталося, коли (UTC) і під яким номером."""

    sensor: SensorRef
    event_type: EventType
    seq: int
    occurred_at: datetime


@dataclass(frozen=True)
class Decision:
    """Результат обробки спрацювання: рівень тривоги й перехід режиму."""

    level: AlarmLevel
    confidence: Decimal
    mode_trigger: ModeTrigger | None


def is_duplicate(
    reading: Reading, previous: Iterable[Reading], window: timedelta
) -> bool:
    """Дублікат: та сама подія того самого датчика з тим самим номером або
    в межах вікна Δ(дубл.): |t(e) − t(e')| < Δ або seq(e) = seq(e')."""
    return any(
        prior.sensor.sensor_id == reading.sensor.sensor_id
        and prior.event_type == reading.event_type
        and (
            prior.seq == reading.seq
            or abs(prior.occurred_at - reading.occurred_at) < window
        )
        for prior in previous
    )


def is_instant(reading: Reading) -> bool:
    """Тампер або цілодобова зона: тривога без затримки в будь-якому режимі."""
    return (
        reading.sensor.sensor_type == SensorType.TAMPER
        or reading.sensor.zone_type == ZoneType.ALWAYS_ON
    )


def is_monitored(mode: FacilityMode, reading: Reading) -> bool:
    """Чи обробляється спрацювання в поточному режимі (крок 4 конвеєра)."""
    if reading.event_type not in TRIGGER_EVENTS:
        return False
    if is_instant(reading):
        return True
    if mode in UNGUARDED_MODES:
        return False
    if mode == FacilityMode.ARMED_HOME:
        # «Вдома»: внутрішні зони й датчики руху виключено з обробки.
        return (
            reading.sensor.zone_type != ZoneType.INTERIOR
            and reading.sensor.sensor_type != SensorType.PIR
        )
    return True


def confidence_index(
    readings: Iterable[Reading], now: datetime, settings: RuleSettings
) -> Decimal:
    """C(t) = Σ w(i) по різних датчиках, що спрацювали в [t − Δ(підтв.), t].

    Повторні спрацювання одного датчика у вікні не додаються.
    """
    window_start = now - settings.confirm_window
    sensor_types = {
        reading.sensor.sensor_id: reading.sensor.sensor_type
        for reading in readings
        if window_start <= reading.occurred_at <= now
    }
    return sum(
        (settings.weights[sensor_type] for sensor_type in sensor_types.values()),
        Decimal(0),
    )


def classify(confidence: Decimal, settings: RuleSettings) -> AlarmLevel:
    """Рівень тривоги за індексом достовірності та порогами об'єкта."""
    if confidence >= settings.confirmed_threshold:
        return AlarmLevel.CONFIRMED
    if confidence >= settings.alarm_threshold:
        return AlarmLevel.ALARM
    return AlarmLevel.WARNING


def raise_level(current: AlarmLevel | None, new: AlarmLevel) -> AlarmLevel:
    """Рівень наявної тривоги може лише підвищуватися."""
    if current is None or LEVEL_ORDER[new] > LEVEL_ORDER[current]:
        return new
    return current


def evaluate(
    reading: Reading,
    mode: FacilityMode,
    recent: Sequence[Reading],
    settings: RuleSettings,
) -> Decision | None:
    """Кроки 4–5 конвеєра: відсів за режимом, індекс достовірності, рівень.

    recent — попередні спрацювання об'єкта (без поточного); враховуються
    лише ті, що обробляються в поточному режимі. Повертає None, якщо подія
    лише архівується.
    """
    if not is_monitored(mode, reading):
        return None
    considered = [prior for prior in recent if is_monitored(mode, prior)]
    confidence = confidence_index([*considered, reading], reading.occurred_at, settings)
    if is_instant(reading):
        return Decision(AlarmLevel.CONFIRMED, confidence, ModeTrigger.INSTANT_ALARM)
    level = classify(confidence, settings)
    trigger = None
    if mode in ARMED_MODES and level != AlarmLevel.WARNING:
        trigger = ModeTrigger.INTRUSION
    return Decision(level, confidence, trigger)
