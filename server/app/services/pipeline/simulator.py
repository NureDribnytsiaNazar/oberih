"""Відтворення тестового сценарію в ізольованому режимі (ФМ-6).

Кроки сценарію проходять через те саме ядро конвеєра (core.py) і той
самий автомат режимів, але в пам'яті: без запису подій і тривог у БД,
без сповіщень, із віртуальним годинником від початку сценарію.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.models.enums import AlarmLevel, EventType, FacilityMode
from app.services.pipeline.core import (
    TRIGGER_EVENTS,
    Decision,
    Reading,
    RuleSettings,
    SensorRef,
    evaluate,
    is_duplicate,
    raise_level,
)
from app.services.state_machine import expired_delay_trigger, next_mode

# Віртуальний годинник: точка відліку не залежить від реального часу.
VIRTUAL_START = datetime(2000, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class ScenarioStep:
    """Крок сценарію: зміщення від початку, датчик, нова подія."""

    offset_ms: int
    sensor: SensorRef
    event_type: EventType


@dataclass
class SimulatedAlarm:
    """Тривога, що виникла під час відтворення."""

    zone_id: Any
    level: AlarmLevel
    confidence: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level.value, "zone_id": str(self.zone_id)}


@dataclass
class SimulationResult:
    """Підсумок відтворення."""

    alarms: list[SimulatedAlarm]
    final_mode: FacilityMode
    duplicates: int


@dataclass
class _State:
    mode: FacilityMode
    mode_changed_at: datetime
    history: list[Reading] = field(default_factory=list)
    alarms: list[SimulatedAlarm] = field(default_factory=list)
    open_alarm: SimulatedAlarm | None = None
    duplicates: int = 0


def replay(
    steps: Sequence[ScenarioStep], mode: FacilityMode, settings: RuleSettings
) -> SimulationResult:
    """Проганяє кроки сценарію через конвеєр і автомат режимів."""
    state = _State(mode=mode, mode_changed_at=VIRTUAL_START)
    for seq, step in enumerate(sorted(steps, key=lambda s: s.offset_ms), start=1):
        now = VIRTUAL_START + timedelta(milliseconds=step.offset_ms)
        _advance_timers(state, now, settings)
        _process(state, Reading(step.sensor, step.event_type, seq, now), settings)
    # Після останнього кроку даємо спливти затримці входу.
    last = state.history[-1].occurred_at if state.history else VIRTUAL_START
    _advance_timers(state, last + timedelta(seconds=settings.entry_delay_s), settings)
    return SimulationResult(state.alarms, state.mode, state.duplicates)


def compare(
    expected: Iterable[dict[str, Any]], actual: Iterable[SimulatedAlarm]
) -> list[dict[str, Any]]:
    """Розбіжності між очікуваними й отриманими тривогами.

    Очікувана тривога задається рівнем і (необов'язково) зоною; порядок
    тривог не має значення.
    """
    remaining = list(actual)
    mismatches: list[dict[str, Any]] = []
    for item in expected:
        match = next((alarm for alarm in remaining if _matches(item, alarm)), None)
        if match is None:
            mismatches.append({"kind": "missing", "expected": item})
        else:
            remaining.remove(match)
    mismatches.extend(
        {"kind": "unexpected", "actual": alarm.as_dict()} for alarm in remaining
    )
    return mismatches


def _process(state: _State, reading: Reading, settings: RuleSettings) -> None:
    if is_duplicate(reading, state.history, settings.duplicate_window):
        state.duplicates += 1
        return
    window_start = reading.occurred_at - settings.confirm_window
    recent = [
        prior
        for prior in state.history
        if prior.event_type in TRIGGER_EVENTS
        and prior.sensor.sensor_id != reading.sensor.sensor_id
        and window_start <= prior.occurred_at <= reading.occurred_at
    ]
    state.history.append(reading)
    decision = evaluate(reading, state.mode, recent, settings)
    if decision is not None:
        _apply(state, reading, decision, settings)


def _apply(
    state: _State, reading: Reading, decision: Decision, settings: RuleSettings
) -> None:
    if state.open_alarm is None:
        state.open_alarm = SimulatedAlarm(
            reading.sensor.zone_id, decision.level, decision.confidence
        )
        state.alarms.append(state.open_alarm)
    else:
        state.open_alarm.level = raise_level(state.open_alarm.level, decision.level)
        state.open_alarm.confidence = max(
            state.open_alarm.confidence, decision.confidence
        )
    if decision.mode_trigger is not None:
        delay = settings.entry_delay_s
        _set_mode(state, next_mode(state.mode, decision.mode_trigger, delay), reading)


def _advance_timers(state: _State, now: datetime, settings: RuleSettings) -> None:
    trigger = expired_delay_trigger(
        state.mode,
        state.mode_changed_at,
        settings.exit_delay_s,
        settings.entry_delay_s,
        now,
    )
    if trigger is not None:
        state.mode = next_mode(state.mode, trigger)
        state.mode_changed_at = now


def _set_mode(state: _State, mode: FacilityMode, reading: Reading) -> None:
    if mode != state.mode:
        state.mode = mode
        state.mode_changed_at = reading.occurred_at


def _matches(expected: dict[str, Any], alarm: SimulatedAlarm) -> bool:
    if expected.get("level") != alarm.level.value:
        return False
    zone = expected.get("zone_id")
    return zone is None or str(zone) == str(alarm.zone_id)
