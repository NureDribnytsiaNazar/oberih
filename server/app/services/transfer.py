"""Експорт та імпорт налаштувань об'єкта (ФМ-9, критерій 3.3).

Імпорт працює в одній транзакції. Режим dry_run виконує ті самі кроки й
відкочує транзакцію, тому звіт «що буде змінено» гарантовано збігається
з реальним імпортом. Повторний імпорт того самого документа нічого не
змінює (ідемпотентність за природними ключами).
"""

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import BadRequestError
from app.models.devices import Node, Sensor
from app.models.events import TestScenario
from app.models.facilities import Facility, Schedule, Zone
from app.models.users import User
from app.schemas.facilities import FacilitySettingsUpdate
from app.schemas.transfer import (
    ExpectedDoc,
    ImportReport,
    NodeDoc,
    ScenarioDoc,
    ScheduleDoc,
    SensorDoc,
    SettingsDocument,
    StepDoc,
    ZoneDoc,
)
from app.services import audit
from app.services.users import validate_timezone

SECTIONS = ("settings", "zones", "nodes", "sensors", "schedules", "scenarios")


class _Tally:
    """Підрахунок створених, змінених і незмінних записів."""

    def __init__(self) -> None:
        self.created: Counter[str] = Counter()
        self.updated: Counter[str] = Counter()
        self.unchanged: Counter[str] = Counter()

    def apply(self, section: str, entity: Any, values: dict[str, Any]) -> None:
        """Записує в модель лише змінені значення й рахує результат."""
        changed = {k: v for k, v in values.items() if getattr(entity, k) != v}
        for key, value in changed.items():
            setattr(entity, key, value)
        (self.updated if changed else self.unchanged)[section] += 1

    def report(self, dry_run: bool) -> ImportReport:
        def full(counter: Counter[str]) -> dict[str, int]:
            return {section: counter[section] for section in SECTIONS}

        return ImportReport(
            dry_run=dry_run,
            created=full(self.created),
            updated=full(self.updated),
            unchanged=full(self.unchanged),
        )


# --- Експорт -----------------------------------------------------------------


def export_settings(db: Session, facility: Facility) -> SettingsDocument:
    """Документ налаштувань об'єкта зі стабільними іменами полів."""
    zones = _zones(db, facility)
    zone_names = {zone.id: zone.name for zone in zones.values()}
    nodes = list(db.scalars(select(Node).where(Node.facility_id == facility.id)))
    sensor_keys = {
        sensor.id: (node.serial, sensor.channel)
        for node in nodes
        for sensor in node.sensors
    }
    return SettingsDocument(
        exported_at=datetime.now(UTC),
        timezone=facility.timezone,
        settings=_settings_doc(facility),
        zones=[ZoneDoc(name=z.name, zone_type=z.zone_type) for z in zones.values()],
        nodes=[_node_doc(node, zone_names) for node in nodes],
        schedules=[
            ScheduleDoc(
                name=s.name,
                action=s.action,
                days_mask=s.days_mask,
                local_time=s.local_time,
                enabled=s.enabled,
            )
            for s in db.scalars(
                select(Schedule).where(Schedule.facility_id == facility.id)
            )
        ],
        scenarios=[
            _scenario_doc(scenario, sensor_keys, zone_names)
            for scenario in db.scalars(
                select(TestScenario).where(TestScenario.facility_id == facility.id)
            )
        ],
    )


def _settings_doc(facility: Facility) -> FacilitySettingsUpdate:
    return FacilitySettingsUpdate.model_validate(
        facility.settings, from_attributes=True
    )


def _node_doc(node: Node, zone_names: dict[uuid.UUID, str]) -> NodeDoc:
    return NodeDoc(
        serial=node.serial,
        name=node.name,
        sensors=[
            SensorDoc(
                channel=sensor.channel,
                name=sensor.name,
                sensor_type=sensor.sensor_type,
                zone=zone_names[sensor.zone_id],
                is_enabled=sensor.is_enabled,
            )
            for sensor in sorted(node.sensors, key=lambda s: s.channel)
        ],
    )


def _scenario_doc(
    scenario: TestScenario,
    sensor_keys: dict[uuid.UUID, tuple[str, int]],
    zone_names: dict[uuid.UUID, str],
) -> ScenarioDoc:
    steps = []
    for step in scenario.steps:
        serial, channel = sensor_keys[uuid.UUID(step["sensor_id"])]
        steps.append(
            StepDoc(
                offset_ms=step["offset_ms"],
                node_serial=serial,
                channel=channel,
                state=step["state"],
            )
        )
    expected = [
        ExpectedDoc(
            level=item["level"],
            zone=(
                zone_names.get(uuid.UUID(item["zone_id"]))
                if item.get("zone_id")
                else None
            ),
        )
        for item in scenario.expected
    ]
    return ScenarioDoc(
        name=scenario.name,
        description=scenario.description,
        steps=steps,
        expected=expected,
    )


# --- Імпорт ------------------------------------------------------------------


def import_settings(
    db: Session, facility: Facility, user: User, doc: SettingsDocument, dry_run: bool
) -> ImportReport:
    """Застосовує документ до об'єкта; dry_run нічого не записує."""
    tally = _Tally()
    if doc.timezone is not None:
        facility.timezone = validate_timezone(doc.timezone)
    _import_facility_settings(facility, doc, tally)
    zones = _import_zones(db, facility, doc.zones, tally)
    sensors = _import_nodes(db, facility, doc.nodes, zones, tally)
    _import_schedules(db, facility, doc.schedules, tally)
    _import_scenarios(db, facility, user, doc.scenarios, zones, sensors, tally)
    db.flush()
    report = tally.report(dry_run)
    if dry_run:
        db.rollback()
        return report
    audit.record(
        db, user.id, "facility.import", "facility", facility.id, report.created
    )
    db.commit()
    return report


def _import_facility_settings(
    facility: Facility, doc: SettingsDocument, tally: _Tally
) -> None:
    values = doc.settings.model_dump(exclude_none=True)
    tally.apply("settings", facility.settings, values)


def _import_zones(
    db: Session, facility: Facility, docs: list[ZoneDoc], tally: _Tally
) -> dict[str, Zone]:
    zones = _zones(db, facility)
    for doc in docs:
        zone = zones.get(doc.name)
        if zone is None:
            zone = Zone(facility_id=facility.id, name=doc.name, zone_type=doc.zone_type)
            db.add(zone)
            zones[doc.name] = zone
            tally.created["zones"] += 1
        else:
            tally.apply("zones", zone, {"zone_type": doc.zone_type})
    db.flush()
    return zones


def _import_nodes(
    db: Session,
    facility: Facility,
    docs: list[NodeDoc],
    zones: dict[str, Zone],
    tally: _Tally,
) -> dict[tuple[str, int], Sensor]:
    sensors: dict[tuple[str, int], Sensor] = {}
    for index, doc in enumerate(docs):
        node = db.scalar(select(Node).where(Node.serial == doc.serial))
        if node is not None and node.facility_id != facility.id:
            raise _invalid(["nodes", index, "serial"], "belongs to another facility")
        if node is None:
            node = Node(facility_id=facility.id, serial=doc.serial, name=doc.name)
            db.add(node)
            tally.created["nodes"] += 1
        else:
            tally.apply("nodes", node, {"name": doc.name})
        for position, sensor_doc in enumerate(doc.sensors):
            loc = ["nodes", index, "sensors", position]
            sensor = _import_sensor(node, sensor_doc, zones, tally, loc)
            sensors[(doc.serial, sensor_doc.channel)] = sensor
    db.flush()
    return sensors


def _import_sensor(
    node: Node,
    doc: SensorDoc,
    zones: dict[str, Zone],
    tally: _Tally,
    loc: list[Any],
) -> Sensor:
    zone = zones.get(doc.zone)
    if zone is None:
        raise _invalid([*loc, "zone"], "unknown zone")
    values = {
        "name": doc.name,
        "sensor_type": doc.sensor_type,
        "zone_id": zone.id,
        "is_enabled": doc.is_enabled,
    }
    sensor = next((s for s in node.sensors if s.channel == doc.channel), None)
    if sensor is None:
        sensor = Sensor(channel=doc.channel, **values)
        node.sensors.append(sensor)
        tally.created["sensors"] += 1
    else:
        tally.apply("sensors", sensor, values)
    return sensor


def _import_schedules(
    db: Session, facility: Facility, docs: list[ScheduleDoc], tally: _Tally
) -> None:
    existing = {
        s.name: s
        for s in db.scalars(select(Schedule).where(Schedule.facility_id == facility.id))
    }
    for doc in docs:
        values = doc.model_dump(exclude={"name"})
        schedule = existing.get(doc.name)
        if schedule is None:
            db.add(Schedule(facility_id=facility.id, name=doc.name, **values))
            tally.created["schedules"] += 1
        else:
            tally.apply("schedules", schedule, values)


def _import_scenarios(
    db: Session,
    facility: Facility,
    user: User,
    docs: list[ScenarioDoc],
    zones: dict[str, Zone],
    sensors: dict[tuple[str, int], Sensor],
    tally: _Tally,
) -> None:
    existing = {
        s.name: s
        for s in db.scalars(
            select(TestScenario).where(TestScenario.facility_id == facility.id)
        )
    }
    known = {**_facility_sensors(db, facility), **sensors}
    for index, doc in enumerate(docs):
        values = {
            "description": doc.description,
            "steps": [
                _step_json(step, known, index, i) for i, step in enumerate(doc.steps)
            ],
            "expected": [_expected_json(item, zones) for item in doc.expected],
        }
        scenario = existing.get(doc.name)
        if scenario is None:
            db.add(
                TestScenario(
                    facility_id=facility.id, name=doc.name, created_by=user.id, **values
                )
            )
            tally.created["scenarios"] += 1
        else:
            tally.apply("scenarios", scenario, values)


def _step_json(
    step: StepDoc, sensors: dict[tuple[str, int], Sensor], scenario: int, index: int
) -> dict[str, Any]:
    sensor = sensors.get((step.node_serial, step.channel))
    if sensor is None:
        raise _invalid(["scenarios", scenario, "steps", index], "unknown sensor")
    return {
        "offset_ms": step.offset_ms,
        "sensor_id": str(sensor.id),
        "state": step.state.value,
    }


def _expected_json(item: ExpectedDoc, zones: dict[str, Zone]) -> dict[str, Any]:
    zone = zones.get(item.zone) if item.zone else None
    return {"level": item.level.value, "zone_id": str(zone.id) if zone else None}


def _zones(db: Session, facility: Facility) -> dict[str, Zone]:
    stmt = select(Zone).where(Zone.facility_id == facility.id).order_by(Zone.name)
    return {zone.name: zone for zone in db.scalars(stmt)}


def _facility_sensors(db: Session, facility: Facility) -> dict[tuple[str, int], Sensor]:
    rows = db.execute(
        select(Node.serial, Sensor)
        .join(Sensor, Sensor.node_id == Node.id)
        .where(Node.facility_id == facility.id)
    ).all()
    return {(serial, sensor.channel): sensor for serial, sensor in rows}


def _invalid(loc: list[Any], message: str) -> BadRequestError:
    """Помилка імпорту з місцем у документі (як у помилках валідації)."""
    return BadRequestError("import_invalid", [{"loc": loc, "msg": message}])
