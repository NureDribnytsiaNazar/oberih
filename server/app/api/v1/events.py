"""Маршрути архіву подій і тривог."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.deps import CurrentUser, DbSession, Paging
from app.models.enums import AlarmLevel, AlarmStatus, EventType
from app.pagination import page_response
from app.schemas.common import Page
from app.schemas.events import AcknowledgeRequest, AlarmOut, EventOut
from app.services import alarms as service
from app.services.access import Permission, require_access

router = APIRouter(tags=["events"])


@router.get("/facilities/{facility_id}/events", response_model=Page[EventOut])
def list_events(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    paging: Paging,
    occurred_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    event_type: EventType | None = None,
    zone_id: uuid.UUID | None = None,
) -> object:
    """Архів подій із фільтрами за часом [from, to), типом і зоною."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    page = service.list_events(
        db, facility, paging, occurred_from, occurred_to, event_type, zone_id
    )
    return page_response(page, paging)


@router.get("/facilities/{facility_id}/alarms", response_model=Page[AlarmOut])
def list_alarms(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    paging: Paging,
    status: AlarmStatus | None = None,
    level: AlarmLevel | None = None,
) -> object:
    """Тривоги об'єкта з фільтрами за станом і рівнем."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    page = service.list_alarms(db, facility, paging, status, level)
    return page_response(page, paging)


@router.post("/alarms/{alarm_id}/acknowledge", response_model=AlarmOut)
def acknowledge_alarm(
    alarm_id: uuid.UUID, data: AcknowledgeRequest, user: CurrentUser, db: DbSession
) -> object:
    """Підтвердження, позначка «хибна» або закриття тривоги."""
    return service.acknowledge(db, user, alarm_id, data)
