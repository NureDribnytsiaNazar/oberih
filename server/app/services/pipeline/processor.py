"""Обробка пакета подій вузла: ядро конвеєра + робота з БД.

Кроки (розділ 2.2.2 Vision & Scope): 1) пакет уже автентифіковано й
провалідовано; 2) усунення дублікатів; 3) запис в архів із міткою часу
вузла; 4–5) відсів за режимом, індекс достовірності й рівень (core.py);
6) тривога, перехід режиму, сповіщення.
"""

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import BadRequestError
from app.models.devices import Node, Sensor
from app.models.enums import ActionSource
from app.models.events import Event
from app.models.facilities import Facility, Zone
from app.schemas.events import (
    DeviceEventBatch,
    DeviceEventIn,
    DeviceEventResult,
    DeviceEventsResult,
)
from app.services import arming, nodes
from app.services.alarm_store import record_decision
from app.services.notifier import notifier
from app.services.pipeline.core import (
    TRIGGER_EVENTS,
    Decision,
    Reading,
    RuleSettings,
    SensorRef,
    evaluate,
)


def ingest_batch(
    db: Session, node: Node, batch: DeviceEventBatch, now: datetime | None = None
) -> DeviceEventsResult:
    """Обробляє пакет подій вузла атомарно (одна транзакція).

    Якщо хоча б одна подія містить невідомий канал, не записується жодна.
    """
    now = now or datetime.now(UTC)
    facility = db.get_one(Facility, node.facility_id)
    sensors = _sensor_refs(db, node)
    if any(item.channel not in sensors for item in batch.events):
        raise BadRequestError("unknown_channel")

    settings = RuleSettings.from_model(facility.settings)
    arming.apply_due_timer(db, facility, now)
    nodes.mark_seen(db, node, now)

    results = []
    for item in sorted(batch.events, key=lambda event: (event.occurred_at, event.seq)):
        reading = _reading(item, sensors[item.channel])
        status = _process_reading(db, node, facility, reading, item, settings, now)
        results.append(
            DeviceEventResult(seq=item.seq, channel=item.channel, status=status)
        )

    node.last_seq = max(node.last_seq, *(item.seq for item in batch.events))
    db.commit()
    accepted = sum(1 for result in results if result.status == "accepted")
    return DeviceEventsResult(
        accepted=accepted,
        duplicates=len(results) - accepted,
        last_seq=node.last_seq,
        results=results,
    )


def _process_reading(
    db: Session,
    node: Node,
    facility: Facility,
    reading: Reading,
    item: DeviceEventIn,
    settings: RuleSettings,
    now: datetime,
) -> str:
    """Кроки 2–6 для однієї події. Повертає accepted або duplicate."""
    if _is_stored_duplicate(db, reading, settings):
        return "duplicate"
    event_id = _store_event(db, node, reading, item)
    if event_id is None:
        return "duplicate"  # паралельний запис тієї самої події
    decision = evaluate(
        reading,
        facility.mode,
        _recent_triggers(db, facility, reading, settings),
        settings,
    )
    if decision is not None:
        _apply_decision(db, facility, reading, decision, event_id, now)
    return "accepted"


def _apply_decision(
    db: Session,
    facility: Facility,
    reading: Reading,
    decision: Decision,
    event_id: int,
    now: datetime,
) -> None:
    """Крок 6: тривога, перехід автомата (журнал із джерелом system), сповіщення."""
    alarm = record_decision(
        db, facility.id, reading.sensor.zone_id, decision, event_id, now
    )
    if decision.mode_trigger is not None:
        arming.transition(
            db, facility, decision.mode_trigger, ActionSource.SYSTEM, now=now
        )
    notifier.alarm_changed(alarm)


def _sensor_refs(db: Session, node: Node) -> dict[int, SensorRef]:
    """Канал вузла -> датчик із типом зони (лише ввімкнені датчики)."""
    rows = db.execute(
        select(Sensor, Zone)
        .join(Zone, Zone.id == Sensor.zone_id)
        .where(Sensor.node_id == node.id, Sensor.is_enabled)
    ).all()
    return {
        sensor.channel: SensorRef(
            sensor.id, sensor.sensor_type, zone.id, zone.zone_type
        )
        for sensor, zone in rows
    }


def _reading(item: DeviceEventIn, sensor: SensorRef) -> Reading:
    return Reading(sensor, item.event_type, item.seq, item.occurred_at.astimezone(UTC))


def _is_stored_duplicate(db: Session, reading: Reading, settings: RuleSettings) -> bool:
    """Чи є в архіві та сама подія за номером або в межах вікна Δ(дубл.)."""
    window = settings.duplicate_window
    found = db.scalar(
        select(Event.id)
        .where(
            Event.sensor_id == reading.sensor.sensor_id,
            Event.event_type == reading.event_type,
            or_(
                Event.seq == reading.seq,
                # Строга нерівність: |t(e) − t(e')| < Δ(дубл.).
                (Event.occurred_at > reading.occurred_at - window)
                & (Event.occurred_at < reading.occurred_at + window),
            ),
        )
        .limit(1)
    )
    return found is not None


def _store_event(
    db: Session, node: Node, reading: Reading, item: DeviceEventIn
) -> int | None:
    """Записує подію з початковою міткою часу вузла (UTC)."""
    stmt = (
        insert(Event)
        .values(
            facility_id=node.facility_id,
            node_id=node.id,
            sensor_id=reading.sensor.sensor_id,
            event_type=reading.event_type,
            seq=reading.seq,
            occurred_at=reading.occurred_at,
            payload=item.payload,
        )
        .on_conflict_do_nothing(constraint="uq_events_dedup_key")
        .returning(Event.id)
    )
    return db.scalar(stmt)


def _recent_triggers(
    db: Session, facility: Facility, reading: Reading, settings: RuleSettings
) -> list[Reading]:
    """Попередні спрацювання об'єкта у вікні Δ(підтв.) до поточної події."""
    window_start = reading.occurred_at - settings.confirm_window
    rows = db.execute(
        select(Event, Sensor, Zone)
        .join(Sensor, Sensor.id == Event.sensor_id)
        .join(Zone, Zone.id == Sensor.zone_id)
        .where(
            Event.facility_id == facility.id,
            Event.event_type.in_(TRIGGER_EVENTS),
            Event.occurred_at.between(window_start, reading.occurred_at),
            Event.sensor_id != reading.sensor.sensor_id,
        )
    ).all()
    return [
        Reading(
            SensorRef(sensor.id, sensor.sensor_type, zone.id, zone.zone_type),
            event.event_type,
            event.seq or 0,
            event.occurred_at,
        )
        for event, sensor, zone in rows
    ]
