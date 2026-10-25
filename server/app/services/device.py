"""Приймання подій і службових повідомлень від IoT-вузлів (ФМ-2).

Межа ЛБ2/ЛБ3: тут подія перевіряється, відсіюється як дублікат за ключем
uq_events_dedup_key і записується в архів. Індекс достовірності, тривоги
за правилами, вікно Δ(дубл.) та таймери затримок — ЛБ3.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.errors import BadRequestError
from app.models.devices import Node, Sensor
from app.models.enums import (
    ActionSource,
    AlarmLevel,
    EventType,
    FacilityMode,
    NodeStatus,
)
from app.models.events import Alarm, AlarmEvent, Event
from app.models.facilities import Facility
from app.schemas.events import (
    DeviceEventBatch,
    DeviceEventsResult,
    HeartbeatIn,
    HeartbeatOut,
)
from app.services.arming import change_mode


def ingest_events(
    db: Session, node: Node, batch: DeviceEventBatch
) -> DeviceEventsResult:
    """Записує пакет подій вузла; повторні події не створюють нових записів.

    Пакет обробляється атомарно: якщо хоча б одна подія містить невідомий
    канал, не записується жодна.
    """
    sensors = {
        sensor.channel: sensor
        for sensor in db.scalars(select(Sensor).where(Sensor.node_id == node.id))
    }
    if any(item.channel not in sensors for item in batch.events):
        raise BadRequestError("unknown_channel")

    accepted = 0
    for item in sorted(batch.events, key=lambda event: event.seq):
        sensor = sensors[item.channel]
        stmt = (
            insert(Event)
            .values(
                facility_id=node.facility_id,
                node_id=node.id,
                sensor_id=sensor.id,
                event_type=item.event_type,
                seq=item.seq,
                occurred_at=item.occurred_at,
                payload=item.payload,
            )
            .on_conflict_do_nothing(constraint="uq_events_dedup_key")
            .returning(Event.id)
        )
        event_id = db.scalar(stmt)
        if event_id is None:
            continue  # дублікат: таку подію вже записано раніше
        accepted += 1
        if item.event_type == EventType.TAMPER:
            _tamper_alarm_stub(db, node, sensor, event_id)

    _mark_online(node)
    node.last_seq = max(node.last_seq, *(item.seq for item in batch.events))
    db.commit()
    return DeviceEventsResult(
        accepted=accepted,
        duplicates=len(batch.events) - accepted,
        last_seq=node.last_seq,
    )


def heartbeat(db: Session, node: Node, data: HeartbeatIn) -> HeartbeatOut:
    """Службове повідомлення: вузол на зв'язку, повертаємо його параметри."""
    _mark_online(node)
    if data.firmware_version:
        node.firmware_version = data.firmware_version
    facility = db.get_one(Facility, node.facility_id)
    db.commit()
    return HeartbeatOut(
        server_time=datetime.now(UTC),
        poll_interval_s=facility.settings.poll_interval_s,
        facility_mode=facility.mode,
    )


def _mark_online(node: Node) -> None:
    node.last_seen_at = datetime.now(UTC)
    node.status = NodeStatus.ONLINE


def _tamper_alarm_stub(db: Session, node: Node, sensor: Sensor, event_id: int) -> None:
    """ЗАГЛУШКА ЛБ2: втручання в корпус одразу дає підтверджену тривогу.

    За Vision & Scope тампер переводить систему в тривогу без затримки в
    будь-якому стані (вага 1,0). Повна класифікація подій за індексом
    достовірності буде реалізована в ЛБ3 і замінить цю функцію.
    """
    alarm = Alarm(
        facility_id=node.facility_id,
        zone_id=sensor.zone_id,
        level=AlarmLevel.CONFIRMED,
        confidence=Decimal("1.00"),
    )
    alarm.events.append(AlarmEvent(event_id=event_id))
    db.add(alarm)
    facility = db.get_one(Facility, node.facility_id)
    if facility.mode != FacilityMode.ALARM:
        change_mode(db, facility, FacilityMode.ALARM, ActionSource.DEVICE)
