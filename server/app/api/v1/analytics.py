"""Маршрути статистики хибних спрацювань і тестових сценаріїв."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.deps import CurrentUser, DbSession, Paging, UserLocale
from app.i18n import translate
from app.pagination import page_response
from app.schemas.analytics import (
    FalseAlarmStatsOut,
    FarGroupOut,
    FarSensorOut,
    ScenarioCreate,
    ScenarioOut,
    ScenarioRunOut,
    ScenarioRunRequest,
    ScenarioUpdate,
)
from app.schemas.common import Page
from app.services import scenarios as scenario_service
from app.services.access import Permission, require_access
from app.services.statistics import (
    CHECK_SENSOR,
    FarRow,
    false_alarm_stats,
    needs_check,
)
from app.services.users import validate_timezone

router = APIRouter(prefix="/facilities/{facility_id}", tags=["analytics"])


@router.get("/statistics/false-alarms")
def false_alarms(
    facility_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    locale: UserLocale,
    tz: Annotated[str | None, Query(max_length=64)] = None,
) -> FalseAlarmStatsOut:
    """FAR за датчиками, зонами й годиною доби (у поясі об'єкта або tz)."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    if tz is not None:
        validate_timezone(tz)
    stats = false_alarm_stats(db, facility, datetime.now(UTC), tz)
    settings = facility.settings

    def sensor_out(row: FarRow) -> FarSensorOut:
        check = needs_check(row, settings)
        return FarSensorOut(
            sensor_id=row.key,
            sensor_name=row.name or "",
            alarms=row.alarms,
            false_alarms=row.false_alarms,
            far=row.far,
            recommendation=CHECK_SENSOR if check else None,
            recommendation_text=(
                translate("far.check_sensor", locale) if check else None
            ),
        )

    def group_out(row: FarRow) -> FarGroupOut:
        key = str(int(row.key)) if row.name is None else str(row.key)
        return FarGroupOut(
            key=key,
            name=row.name,
            alarms=row.alarms,
            false_alarms=row.false_alarms,
            far=row.far,
        )

    return FalseAlarmStatsOut(
        since=stats.since,
        window_days=settings.far_window_days,
        timezone=stats.timezone,
        sensors=[sensor_out(row) for row in stats.sensors],
        zones=[group_out(row) for row in stats.zones],
        hours=[group_out(row) for row in stats.hours],
    )


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_scenarios(
    facility_id: uuid.UUID, user: CurrentUser, db: DbSession, locale: UserLocale
) -> object:
    """Тестові сценарії об'єкта (власник, монтажник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return scenario_service.list_scenarios(db, facility, locale)


@router.post(
    "/scenarios", response_model=ScenarioOut, status_code=status.HTTP_201_CREATED
)
def create_scenario(
    facility_id: uuid.UUID, data: ScenarioCreate, user: CurrentUser, db: DbSession
) -> object:
    """Створення сценарію: кроки {offset_ms, sensor_id, state} і очікувані тривоги."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return scenario_service.create_scenario(db, facility, user, data)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario(
    facility_id: uuid.UUID, scenario_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> object:
    """Сценарій об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return scenario_service.get_scenario(db, facility, scenario_id)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(
    facility_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: ScenarioUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна сценарію."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return scenario_service.update_scenario(db, facility, scenario_id, data)


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    facility_id: uuid.UUID, scenario_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Видалення сценарію."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    scenario_service.delete_scenario(db, facility, scenario_id)


@router.post("/scenarios/{scenario_id}/run", response_model=ScenarioRunOut)
def run_scenario(
    facility_id: uuid.UUID,
    scenario_id: uuid.UUID,
    data: ScenarioRunRequest,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Відтворення в ізольованому режимі з поточними налаштуваннями об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return scenario_service.run_scenario(db, facility, scenario_id, data)


@router.get("/scenarios/{scenario_id}/runs", response_model=Page[ScenarioRunOut])
def list_runs(
    facility_id: uuid.UUID,
    scenario_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    paging: Paging,
) -> object:
    """Історія запусків сценарію."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    page = scenario_service.list_runs(db, facility, scenario_id, paging)
    return page_response(page, paging)
