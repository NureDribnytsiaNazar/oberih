"""Тестові сценарії: зберігання та ізольоване відтворення (ФМ-6)."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import BadRequestError
from app.l10n import collated
from app.models.devices import Node, Sensor
from app.models.enums import Locale
from app.models.events import ScenarioRun, TestScenario
from app.models.facilities import Facility, Zone
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.analytics import (
    ScenarioCreate,
    ScenarioRunRequest,
    ScenarioStepIn,
    ScenarioUpdate,
)
from app.services.common import get_in_facility
from app.services.pipeline.core import RuleSettings, SensorRef
from app.services.pipeline.simulator import ScenarioStep, compare, replay


def list_scenarios(
    db: Session, facility: Facility, locale: Locale
) -> list[TestScenario]:
    """Сценарії об'єкта за назвою (за правилами сортування мови)."""
    return list(
        db.scalars(
            select(TestScenario)
            .where(TestScenario.facility_id == facility.id)
            .order_by(collated(TestScenario.name, locale))
        )
    )


def get_scenario(
    db: Session, facility: Facility, scenario_id: uuid.UUID
) -> TestScenario:
    """Сценарій об'єкта за ідентифікатором."""
    return get_in_facility(db, TestScenario, scenario_id, facility.id)


def create_scenario(
    db: Session, facility: Facility, user: User, data: ScenarioCreate
) -> TestScenario:
    """Зберігає сценарій; усі датчики кроків мають належати об'єкту."""
    _sensor_refs(db, facility, data.steps)
    scenario = TestScenario(
        facility_id=facility.id,
        name=data.name,
        description=data.description,
        steps=[step.model_dump(mode="json") for step in data.steps],
        expected=[item.model_dump(mode="json") for item in data.expected],
        created_by=user.id,
    )
    db.add(scenario)
    db.commit()
    return scenario


def update_scenario(
    db: Session, facility: Facility, scenario_id: uuid.UUID, data: ScenarioUpdate
) -> TestScenario:
    """Змінює назву, опис, кроки або очікувані тривоги."""
    scenario = get_scenario(db, facility, scenario_id)
    if data.name is not None:
        scenario.name = data.name
    if data.description is not None:
        scenario.description = data.description
    if data.steps is not None:
        _sensor_refs(db, facility, data.steps)
        scenario.steps = [step.model_dump(mode="json") for step in data.steps]
    if data.expected is not None:
        scenario.expected = [item.model_dump(mode="json") for item in data.expected]
    db.commit()
    return scenario


def delete_scenario(db: Session, facility: Facility, scenario_id: uuid.UUID) -> None:
    """Видаляє сценарій разом із результатами запусків."""
    db.delete(get_scenario(db, facility, scenario_id))
    db.commit()


def run_scenario(
    db: Session, facility: Facility, scenario_id: uuid.UUID, data: ScenarioRunRequest
) -> ScenarioRun:
    """Відтворює сценарій із поточними налаштуваннями об'єкта.

    Реальні події й тривоги об'єкта не змінюються; зберігається лише
    результат запуску з розбіжностями.
    """
    scenario = get_scenario(db, facility, scenario_id)
    steps_in = [ScenarioStepIn.model_validate(step) for step in scenario.steps]
    sensors = _sensor_refs(db, facility, steps_in)
    steps = [
        ScenarioStep(step.offset_ms, sensors[step.sensor_id], step.state)
        for step in steps_in
    ]
    result = replay(steps, data.mode, RuleSettings.from_model(facility.settings))
    mismatches = compare(scenario.expected, result.alarms)
    run = ScenarioRun(
        scenario_id=scenario.id,
        passed=not mismatches,
        actual=[alarm.as_dict() for alarm in result.alarms],
        mismatches=mismatches,
    )
    db.add(run)
    db.commit()
    return run


def list_runs(
    db: Session, facility: Facility, scenario_id: uuid.UUID, params: PageParams
) -> tuple[list[ScenarioRun], int]:
    """Запуски сценарію, найновіші першими."""
    scenario = get_scenario(db, facility, scenario_id)
    stmt = (
        select(ScenarioRun)
        .where(ScenarioRun.scenario_id == scenario.id)
        .order_by(ScenarioRun.started_at.desc(), ScenarioRun.id)
    )
    return paginate(db, stmt, params)


def _sensor_refs(
    db: Session, facility: Facility, steps: list[ScenarioStepIn]
) -> dict[uuid.UUID, SensorRef]:
    """Датчики кроків сценарію; чужий або видалений датчик — помилка."""
    ids = {step.sensor_id for step in steps}
    rows: list[Any] = list(
        db.execute(
            select(Sensor, Zone)
            .join(Zone, Zone.id == Sensor.zone_id)
            .join(Node, Node.id == Sensor.node_id)
            .where(Sensor.id.in_(ids), Node.facility_id == facility.id)
        ).all()
    )
    refs = {
        sensor.id: SensorRef(sensor.id, sensor.sensor_type, zone.id, zone.zone_type)
        for sensor, zone in rows
    }
    if set(refs) != ids:
        raise BadRequestError("scenario_sensor_missing")
    return refs
