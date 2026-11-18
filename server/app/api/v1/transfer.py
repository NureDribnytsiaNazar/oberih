"""Маршрути експорту та імпорту налаштувань і експорту подій у CSV."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from pydantic import AwareDatetime

from app.deps import CurrentUser, DbSession, UserLocale
from app.models.enums import Locale
from app.schemas.transfer import ImportReport, SettingsDocument
from app.services import transfer as service
from app.services.access import Permission, require_access
from app.services.events_export import events_csv
from app.services.users import validate_timezone

router = APIRouter(prefix="/facilities/{facility_id}", tags=["transfer"])


@router.get("/export")
def export_settings(
    facility_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> SettingsDocument:
    """Документ налаштувань: параметри, зони, вузли, датчики, розклади, сценарії."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.export_settings(db, facility)


@router.post("/import")
def import_settings(
    facility_id: uuid.UUID,
    document: SettingsDocument,
    user: CurrentUser,
    db: DbSession,
    dry_run: bool = False,
) -> ImportReport:
    """Імпорт документа; dry_run=true показує зміни, нічого не записуючи."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.import_settings(db, facility, user, document, dry_run)


@router.get(
    "/events/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def export_events(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    user_locale: UserLocale,
    export_format: Annotated[Literal["csv"], Query(alias="format")] = "csv",
    locale: Locale | None = None,
    tz: Annotated[str | None, Query(max_length=64)] = None,
    occurred_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> Response:
    """Архів подій у CSV (UTF-8); роздільник і формат дат — за локаллю."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    tz_name = validate_timezone(tz or user.timezone)
    content = "".join(
        events_csv(
            db, facility, locale or user_locale, tz_name, occurred_from, occurred_to
        )
    )
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="events.csv"'},
    )
