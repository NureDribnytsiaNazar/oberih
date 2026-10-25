"""Архів подій і обробка тривог користувачами (ФМ-5, ФМ-6)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.devices import Sensor
from app.models.enums import AckAction, AlarmLevel, AlarmStatus, EventType
from app.models.events import Alarm, AlarmAcknowledgement, Event
from app.models.facilities import Facility
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.events import AcknowledgeRequest
from app.services.access import Permission, require_access
from app.services.reauth import confirm_action


def list_events(
    db: Session,
    facility: Facility,
    params: PageParams,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    event_type: EventType | None = None,
    zone_id: uuid.UUID | None = None,
) -> tuple[list[Event], int]:
    """Події об'єкта з фільтрами за часом, типом і зоною; новіші першими."""
    stmt: Select[Event] = select(Event).where(Event.facility_id == facility.id)
    if occurred_from is not None:
        stmt = stmt.where(Event.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(Event.occurred_at < occurred_to)
    if event_type is not None:
        stmt = stmt.where(Event.event_type == event_type)
    if zone_id is not None:
        stmt = stmt.join(Sensor, Sensor.id == Event.sensor_id).where(
            Sensor.zone_id == zone_id
        )
    stmt = stmt.order_by(Event.occurred_at.desc(), Event.id.desc())
    return paginate(db, stmt, params)


def list_alarms(
    db: Session,
    facility: Facility,
    params: PageParams,
    status: AlarmStatus | None = None,
    level: AlarmLevel | None = None,
) -> tuple[list[Alarm], int]:
    """Тривоги об'єкта з фільтрами за станом і рівнем; новіші першими."""
    stmt = select(Alarm).where(Alarm.facility_id == facility.id)
    if status is not None:
        stmt = stmt.where(Alarm.status == status)
    if level is not None:
        stmt = stmt.where(Alarm.level == level)
    stmt = stmt.order_by(Alarm.opened_at.desc(), Alarm.id)
    return paginate(db, stmt, params)


def acknowledge(
    db: Session, user: User, alarm_id: uuid.UUID, data: AcknowledgeRequest
) -> Alarm:
    """Підтвердження, позначення хибною або закриття тривоги.

    Дію виконує лише уповноважений користувач після повторного
    підтвердження; кожна дія додається до журналу підтверджень.
    """
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError()
    require_access(db, alarm.facility_id, user, Permission.ACK_ALARM)
    if alarm.status == AlarmStatus.RESOLVED:
        raise ConflictError("alarm_closed")
    method = confirm_action(user, data.confirmation)

    now = datetime.now(UTC)
    if data.action == AckAction.ACKNOWLEDGE:
        alarm.status = AlarmStatus.ACKNOWLEDGED
    elif data.action == AckAction.MARK_FALSE:
        # Позначка «хибна» потрібна для статистики FAR (ЛБ3).
        alarm.is_false = True
        alarm.status = AlarmStatus.RESOLVED
        alarm.closed_at = now
    else:
        alarm.is_false = False if alarm.is_false is None else alarm.is_false
        alarm.status = AlarmStatus.RESOLVED
        alarm.closed_at = now

    db.add(
        AlarmAcknowledgement(
            alarm_id=alarm.id,
            user_id=user.id,
            action=data.action,
            auth_method=method,
            comment=data.comment,
        )
    )
    db.commit()
    return alarm
