"""Чисте ядро конвеєра й автомат режимів (без БД)."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.errors import ConflictError
from app.models.enums import AlarmLevel, EventType, FacilityMode, SensorType, ZoneType
from app.services.pipeline.core import (
    Reading,
    RuleSettings,
    SensorRef,
    confidence_index,
    evaluate,
    is_duplicate,
    raise_level,
)
from app.services.state_machine import ModeTrigger, expired_delay_trigger, next_mode

T0 = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)
SETTINGS = RuleSettings(
    duplicate_window=timedelta(seconds=5),
    confirm_window=timedelta(seconds=60),
    exit_delay_s=30,
    entry_delay_s=30,
    weights={
        SensorType.REED: Decimal("0.5"),
        SensorType.PIR: Decimal("0.4"),
        SensorType.TAMPER: Decimal("1.0"),
    },
    alarm_threshold=Decimal("0.4"),
    confirmed_threshold=Decimal("0.9"),
)
DOOR = SensorRef(uuid.uuid4(), SensorType.REED, uuid.uuid4(), ZoneType.PERIMETER)
WINDOW = SensorRef(uuid.uuid4(), SensorType.REED, uuid.uuid4(), ZoneType.PERIMETER)
HALL = SensorRef(uuid.uuid4(), SensorType.PIR, uuid.uuid4(), ZoneType.INTERIOR)
CASE = SensorRef(uuid.uuid4(), SensorType.TAMPER, uuid.uuid4(), ZoneType.ALWAYS_ON)


def reading(
    sensor: SensorRef, seconds: float, seq: int, event: EventType | None = None
) -> Reading:
    default = {
        SensorType.REED: EventType.OPENED,
        SensorType.PIR: EventType.MOTION,
        SensorType.TAMPER: EventType.TAMPER,
    }[sensor.sensor_type]
    return Reading(sensor, event or default, seq, T0 + timedelta(seconds=seconds))


# --- Усунення дублікатів -----------------------------------------------------


def test_duplicate_by_same_seq() -> None:
    first = reading(DOOR, 0, seq=7)
    assert is_duplicate(reading(DOOR, 30, seq=7), [first], SETTINGS.duplicate_window)


@pytest.mark.parametrize(
    ("delta", "duplicate"), [(4.9, True), (5.0, False), (5.1, False)]
)
def test_duplicate_window_boundary(delta: float, duplicate: bool) -> None:
    first = reading(DOOR, 0, seq=1)
    second = reading(DOOR, delta, seq=2)
    assert is_duplicate(second, [first], SETTINGS.duplicate_window) is duplicate


def test_other_sensor_or_type_is_not_duplicate() -> None:
    first = reading(DOOR, 0, seq=1)
    assert not is_duplicate(
        reading(WINDOW, 1, seq=2), [first], SETTINGS.duplicate_window
    )
    closed = reading(DOOR, 1, seq=2, event=EventType.CLOSED)
    assert not is_duplicate(closed, [first], SETTINGS.duplicate_window)


# --- Індекс достовірності ----------------------------------------------------


def test_single_reed_gives_alarm() -> None:
    decision = evaluate(reading(DOOR, 0, 1), FacilityMode.ARMED_AWAY, [], SETTINGS)
    assert decision is not None
    assert (decision.confidence, decision.level) == (Decimal("0.5"), AlarmLevel.ALARM)
    assert decision.mode_trigger == ModeTrigger.INTRUSION


def test_reed_and_pir_in_window_give_confirmed() -> None:
    prior = [reading(DOOR, 0, 1)]
    decision = evaluate(reading(HALL, 40, 2), FacilityMode.ENTRY_DELAY, prior, SETTINGS)
    assert decision is not None
    assert (decision.confidence, decision.level) == (
        Decimal("0.9"),
        AlarmLevel.CONFIRMED,
    )


def test_reed_and_pir_outside_window_give_alarm_only() -> None:
    prior = [reading(DOOR, 0, 1)]
    decision = evaluate(reading(HALL, 61, 2), FacilityMode.ARMED_AWAY, prior, SETTINGS)
    assert decision is not None
    assert (decision.confidence, decision.level) == (Decimal("0.4"), AlarmLevel.ALARM)


def test_same_sensor_twice_is_counted_once() -> None:
    readings = [reading(DOOR, 0, 1), reading(DOOR, 20, 2)]
    assert confidence_index(readings, T0 + timedelta(seconds=20), SETTINGS) == Decimal(
        "0.5"
    )


def test_low_confidence_gives_warning_without_entry_delay() -> None:
    weak = replace(
        SETTINGS, weights={**SETTINGS.weights, SensorType.PIR: Decimal("0.2")}
    )
    decision = evaluate(reading(HALL, 0, 1), FacilityMode.ARMED_AWAY, [], weak)
    assert decision is not None
    assert (decision.level, decision.mode_trigger) == (AlarmLevel.WARNING, None)


def test_alarm_level_only_rises() -> None:
    assert raise_level(AlarmLevel.CONFIRMED, AlarmLevel.ALARM) == AlarmLevel.CONFIRMED
    assert raise_level(AlarmLevel.ALARM, AlarmLevel.CONFIRMED) == AlarmLevel.CONFIRMED


# --- Відсів за режимом і зоною -----------------------------------------------


def test_home_mode_ignores_pir_but_not_reed() -> None:
    assert evaluate(reading(HALL, 0, 1), FacilityMode.ARMED_HOME, [], SETTINGS) is None
    decision = evaluate(reading(DOOR, 0, 1), FacilityMode.ARMED_HOME, [], SETTINGS)
    assert decision is not None
    assert decision.mode_trigger == ModeTrigger.INTRUSION


@pytest.mark.parametrize("mode", [FacilityMode.DISARMED, FacilityMode.EXIT_DELAY])
def test_unguarded_modes_only_archive(mode: FacilityMode) -> None:
    assert evaluate(reading(DOOR, 0, 1), mode, [], SETTINGS) is None
    assert evaluate(reading(HALL, 0, 1), mode, [], SETTINGS) is None


@pytest.mark.parametrize("mode", list(FacilityMode))
def test_tamper_is_confirmed_alarm_in_any_mode(mode: FacilityMode) -> None:
    decision = evaluate(reading(CASE, 0, 1), mode, [], SETTINGS)
    assert decision is not None
    assert decision.level == AlarmLevel.CONFIRMED
    assert decision.mode_trigger == ModeTrigger.INSTANT_ALARM


def test_closing_door_is_only_archived() -> None:
    closed = reading(DOOR, 0, 1, event=EventType.CLOSED)
    assert evaluate(closed, FacilityMode.ARMED_AWAY, [], SETTINGS) is None


# --- Автомат режимів ---------------------------------------------------------


def test_intrusion_leads_to_entry_delay_or_alarm_without_delay() -> None:
    armed = FacilityMode.ARMED_AWAY
    assert next_mode(armed, ModeTrigger.INTRUSION, 30) == FacilityMode.ENTRY_DELAY
    assert next_mode(armed, ModeTrigger.INTRUSION, 0) == FacilityMode.ALARM


def test_entry_delay_expires_into_alarm() -> None:
    changed = T0
    before = expired_delay_trigger(
        FacilityMode.ENTRY_DELAY, changed, 30, 30, T0 + timedelta(seconds=29)
    )
    after = expired_delay_trigger(
        FacilityMode.ENTRY_DELAY, changed, 30, 30, T0 + timedelta(seconds=30)
    )
    assert before is None
    assert after == ModeTrigger.ENTRY_DELAY_EXPIRED
    assert next_mode(FacilityMode.ENTRY_DELAY, after) == FacilityMode.ALARM


@pytest.mark.parametrize(
    ("mode", "trigger"),
    [
        (FacilityMode.DISARMED, ModeTrigger.DISARM),
        (FacilityMode.DISARMED, ModeTrigger.INTRUSION),
        (FacilityMode.ARMED_AWAY, ModeTrigger.ENTRY_DELAY_EXPIRED),
        (FacilityMode.ALARM, ModeTrigger.ARM_HOME),
    ],
)
def test_invalid_transitions_raise(mode: FacilityMode, trigger: ModeTrigger) -> None:
    with pytest.raises(ConflictError):
        next_mode(mode, trigger)
