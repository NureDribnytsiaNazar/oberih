"""Маршрути розкладів постановки та зняття з охорони."""

import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.facilities import ScheduleCreate, ScheduleOut, ScheduleUpdate
from app.services import schedules as service
from app.services.access import Permission, require_access

router = APIRouter(prefix="/facilities/{facility_id}/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleOut])
def list_schedules(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> object:
    """Розклади об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return service.list_schedules(db, facility)


@router.post("", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    facility_id: uuid.UUID, data: ScheduleCreate, user: CurrentUser, db: DbSession
) -> object:
    """Створення розкладу (власник, монтажник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.create_schedule(db, facility, data)


@router.patch("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    facility_id: uuid.UUID,
    schedule_id: uuid.UUID,
    data: ScheduleUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна розкладу."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.update_schedule(db, facility, schedule_id, data)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    facility_id: uuid.UUID, schedule_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Видалення розкладу."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    service.delete_schedule(db, facility, schedule_id)
