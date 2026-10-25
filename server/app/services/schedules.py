"""Розклади автоматичної постановки на охорону та зняття з охорони.

У ЛБ2 розклади лише зберігаються; виконання за часом — ЛБ3.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.facilities import Facility, Schedule
from app.schemas.facilities import ScheduleCreate, ScheduleUpdate
from app.services.common import apply_changes, get_in_facility


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
