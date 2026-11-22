"""Розклади автоматичної постановки на охорону та зняття з охорони.

Керування розкладами — CRUD нижче. Виконання — run_due_schedules(), яку
фоновий виконавець викликає на кожному проході (timers.process_timers).
Час розкладу — місцевий час об'єкта (Facility.timezone); біт 0 маски
днів — понеділок, біт 6 — неділя.
"""

import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.models.enums import ActionSource, FacilityMode, ScheduleAction
from app.models.facilities import Facility, Schedule
from app.schemas.facilities import ScheduleCreate, ScheduleUpdate
from app.services import arming, commands
from app.services.common import apply_changes, get_in_facility
from app.services.state_machine import ModeTrigger

# Пропущений запуск, старший за це вікно, не наздоганяється (сервер був
# вимкнений або розклад щойно створено на вже минулий час).
CATCH_UP_WINDOW = timedelta(minutes=10)
ACTION_TRIGGERS = {
    ScheduleAction.ARM_AWAY: ModeTrigger.ARM_AWAY,
    ScheduleAction.ARM_HOME: ModeTrigger.ARM_HOME,
    ScheduleAction.DISARM: ModeTrigger.DISARM,
}
# Під час інциденту розклад охорону не знімає, щоб не заглушити тривогу.
INCIDENT_MODES = frozenset({FacilityMode.ENTRY_DELAY, FacilityMode.ALARM})


def list_schedules(db: Session, facility: Facility) -> list[Schedule]:
    """Розклади об'єкта за часом спрацювання."""
    stmt = (
        select(Schedule)
        .where(Schedule.facility_id == facility.id)
        .order_by(Schedule.local_time, Schedule.name)
    )
    return list(db.scalars(stmt))


def create_schedule(db: Session, facility: Facility, data: ScheduleCreate) -> Schedule:
    """Створює розклад."""
    schedule = Schedule(facility_id=facility.id, **data.model_dump())
    db.add(schedule)
    db.commit()
    return schedule


def update_schedule(
    db: Session, facility: Facility, schedule_id: uuid.UUID, data: ScheduleUpdate
) -> Schedule:
    """Змінює розклад."""
    schedule = get_in_facility(db, Schedule, schedule_id, facility.id)
    apply_changes(schedule, data)
    db.commit()
    return schedule


def delete_schedule(db: Session, facility: Facility, schedule_id: uuid.UUID) -> None:
    """Видаляє розклад."""
    schedule = get_in_facility(db, Schedule, schedule_id, facility.id)
    db.delete(schedule)
    db.commit()


# --- Виконання за часом ---------------------------------------------------------


def due_moment(
    local_time_of_day: time,
    days_mask: int,
    timezone: str,
    last_run_at: datetime | None,
    now: datetime,
) -> datetime | None:
    """Момент запуску розкладу, що настав і ще не виконаний, або None.

    Розглядаються сьогоднішній і вчорашній запуски (на випадок переходу
    через північ). Запуск має припадати на день із маски, бути не
    пізніше now і не старшим за CATCH_UP_WINDOW.
    """
    zone = ZoneInfo(timezone)
    local_now = now.astimezone(zone)
    for days_back in (0, 1):
        day = local_now.date() - timedelta(days=days_back)
        moment = datetime.combine(day, local_time_of_day, tzinfo=zone)
        if moment > local_now or not days_mask & (1 << day.weekday()):
            continue
        if local_now - moment > CATCH_UP_WINDOW:
            return None
        if last_run_at is not None and last_run_at >= moment:
            return None
        return moment
    return None


def run_due_schedules(db: Session, now: datetime) -> int:
    """Виконує розклади, час яких настав. Повертає кількість змін режиму.

    Транзакцію фіксує той, хто викликає (timers.process_timers).
    """
    rows = db.execute(
        select(Schedule, Facility)
        .join(Facility, Facility.id == Schedule.facility_id)
        .where(Schedule.enabled)
        .order_by(Schedule.local_time)
    ).all()
    changed = 0
    for schedule, facility in rows:
        moment = due_moment(
            schedule.local_time,
            schedule.days_mask,
            facility.timezone,
            schedule.last_run_at,
            now,
        )
        if moment is None:
            continue
        schedule.last_run_at = moment
        if _execute(db, facility, schedule.action, now):
            changed += 1
    return changed


def _execute(
    db: Session, facility: Facility, action: ScheduleAction, now: datetime
) -> bool:
    """Застосовує дію розкладу. False — режим не змінився."""
    arming.apply_due_timer(db, facility, now)
    if action == ScheduleAction.DISARM and facility.mode in INCIDENT_MODES:
        return False
    before = facility.mode
    try:
        arming.transition(
            db, facility, ACTION_TRIGGERS[action], ActionSource.SCHEDULE, now=now
        )
    except ConflictError:
        return False  # напр., постановка, коли об'єкт уже під охороною
    if facility.mode == before:
        return False
    commands.enqueue_mode(db, facility, now)
    return True
