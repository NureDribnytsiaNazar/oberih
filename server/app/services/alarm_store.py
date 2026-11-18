"""Робота з поточною (відкритою) тривогою об'єкта.

Об'єкт має не більше однієї поточної тривоги: нові спрацювання додаються
до неї, а рівень лише підвищується. Модуль не залежить від інших
сервісів, тому його використовують і конвеєр, і керування режимом.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AlarmLevel, AlarmStatus
from app.models.events import Alarm, AlarmEvent
from app.services.pipeline.core import Decision, raise_level

ACTIVE_STATUSES = (AlarmStatus.OPEN, AlarmStatus.ACKNOWLEDGED)


def get_open_alarm(db: Session, facility_id: uuid.UUID) -> Alarm | None:
    """Поточна тривога об'єкта (відкрита або підтверджена, ще не закрита)."""
    return db.scalars(
        select(Alarm)
        .where(Alarm.facility_id == facility_id, Alarm.status.in_(ACTIVE_STATUSES))
        .order_by(Alarm.opened_at.desc())
        .limit(1)
    ).first()


def record_decision(
    db: Session,
    facility_id: uuid.UUID,
    zone_id: uuid.UUID,
    decision: Decision,
    event_id: int,
    now: datetime,
) -> Alarm:
    """Створює тривогу або підвищує рівень поточної й додає до неї подію."""
    alarm = get_open_alarm(db, facility_id)
    if alarm is None:
        alarm = Alarm(
            facility_id=facility_id,
            zone_id=zone_id,
            level=decision.level,
            confidence=decision.confidence,
            status=AlarmStatus.OPEN,
            opened_at=now,
        )
        db.add(alarm)
    else:
        alarm.level = raise_level(AlarmLevel(alarm.level), decision.level)
        alarm.confidence = max(Decimal(alarm.confidence), decision.confidence)
    alarm.events.append(AlarmEvent(event_id=event_id))
    db.flush()
    return alarm


def close_open_alarms(
    db: Session, facility_id: uuid.UUID, cancelled: bool, now: datetime | None = None
) -> int:
    """Закриває поточні тривоги об'єкта; повертає їх кількість.

    cancelled=True — охорону знято під час затримки входу (законний вхід),
    такі тривоги не враховуються в статистиці хибних спрацювань.
    """
    status = AlarmStatus.CANCELLED if cancelled else AlarmStatus.RESOLVED
    alarms = db.scalars(
        select(Alarm).where(
            Alarm.facility_id == facility_id, Alarm.status.in_(ACTIVE_STATUSES)
        )
    ).all()
    for alarm in alarms:
        alarm.status = status
        alarm.closed_at = now or datetime.now(UTC)
    return len(alarms)
