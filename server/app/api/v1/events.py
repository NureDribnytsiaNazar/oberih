"""Маршрути архіву подій і тривог."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.deps import CurrentUser, DbSession, Paging, UserLocale
from app.models.enums import AlarmLevel, AlarmStatus, EventType
from app.pagination import page_response
from app.schemas.common import Page
from app.schemas.events import AcknowledgeRequest, AlarmOut, EventOut
from app.services import alarms as service
from app.services.access import Permission, require_access
from app.services.presentation import alarm_view, event_view, viewer_prefs

TimezoneParam = Annotated[
    str | None, Query(max_length=64, description="Часовий пояс IANA")
]

router = APIRouter(tags=["events"])


@router.get("/facilities/{facility_id}/events", response_model=Page[EventOut])
def list_events(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    paging: Paging,
    locale: UserLocale,
    occurred_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    event_type: EventType | None = None,
    zone_id: uuid.UUID | None = None,
    tz: TimezoneParam = None,
) -> object:
    """Архів подій із фільтрами за часом [from, to), типом і зоною.

    Час подається в UTC і в місцевому часі (tz або часовий пояс профілю).
    """
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    prefs = viewer_prefs(user, locale, tz)
    items, total = service.list_events(
        db, facility, paging, occurred_from, occurred_to, event_type, zone_id
    )
    return page_response(([event_view(e, prefs) for e in items], total), paging)


@router.get("/facilities/{facility_id}/alarms", response_model=Page[AlarmOut])
def list_alarms(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    paging: Paging,
    locale: UserLocale,
    status: AlarmStatus | None = None,
    level: AlarmLevel | None = None,
    tz: TimezoneParam = None,
) -> object:
    """Тривоги об'єкта з фільтрами за станом і рівнем."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    prefs = viewer_prefs(user, locale, tz)
    items, total = service.list_alarms(db, facility, paging, status, level)
    return page_response(([alarm_view(a, prefs) for a in items], total), paging)


@router.post("/alarms/{alarm_id}/acknowledge", response_model=AlarmOut)
def acknowledge_alarm(
    alarm_id: uuid.UUID, data: AcknowledgeRequest, user: CurrentUser, db: DbSession
) -> object:
    """Підтвердження, позначка «хибна» або закриття тривоги."""
    return service.acknowledge(db, user, alarm_id, data)
