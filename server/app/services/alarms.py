"""Архів подій і обробка тривог користувачами (ФМ-5, ФМ-6)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models.devices import Sensor
from app.models.enums import (
    AckAction,
    ActionSource,
    AlarmLevel,
    AlarmStatus,
    AuthMethod,
    EventType,
    FacilityMode,
)
from app.models.events import Alarm, AlarmAcknowledgement, Event
from app.models.facilities import Facility
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.events import AcknowledgeRequest
from app.services.access import Permission, require_access
from app.services import commands
from app.services.alarm_store import get_open_alarm
from app.services.arming import transition
from app.services.reauth import confirm_action
from app.services.state_machine import ModeTrigger

CLOSED_STATUSES = (AlarmStatus.RESOLVED, AlarmStatus.CANCELLED)
ALARM_MODES = (FacilityMode.ALARM, FacilityMode.ENTRY_DELAY)


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
    підтвердження; кожна дія додається до журналу підтверджень. Коли
    закрито останню тривогу об'єкта в режимі тривоги чи затримки входу,
    об'єкт знімається з охорони (рисунок 2 Vision & Scope).
    """
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError()
    facility, _ = require_access(db, alarm.facility_id, user, Permission.ACK_ALARM)
    if alarm.status in CLOSED_STATUSES:
        raise ConflictError("alarm_closed")
    method = confirm_action(user, data.confirmation)

    _apply_action(alarm, data.action, datetime.now(UTC))
    db.add(
        AlarmAcknowledgement(
            alarm_id=alarm.id,
            user_id=user.id,
            action=data.action,
            auth_method=method,
            comment=data.comment,
        )
    )
    db.flush()
    if alarm.status == AlarmStatus.RESOLVED:
        _reset_facility(db, facility, user, method)
    db.commit()
    return alarm


def _apply_action(alarm: Alarm, action: AckAction, now: datetime) -> None:
    """Змінює стан тривоги відповідно до дії користувача."""
    if action == AckAction.ACKNOWLEDGE:
        alarm.status = AlarmStatus.ACKNOWLEDGED
        return
    # Позначка «хибна» потрібна для статистики FAR; resolve — справжня тривога.
    alarm.is_false = action == AckAction.MARK_FALSE
    alarm.status = AlarmStatus.RESOLVED
    alarm.closed_at = now


def _reset_facility(
    db: Session, facility: Facility, user: User, method: AuthMethod
) -> None:
    """Після закриття останньої тривоги повертає об'єкт у стан «знято»."""
    if facility.mode not in ALARM_MODES or get_open_alarm(db, facility.id):
        return
    transition(db, facility, ModeTrigger.DISARM, ActionSource.API, user.id, method)
    # Вузли теж мають вимкнути сирену: підписана команда зняття (ІК-7).
    commands.enqueue_mode(db, facility)
