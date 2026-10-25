"""Зони, IoT-вузли та датчики об'єкта."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import BadRequestError, NotFoundError
from app.models.devices import Node, Sensor
from app.models.enums import NodeStatus
from app.models.facilities import Facility, Zone
from app.models.users import User
from app.schemas.facilities import (
    NodeCommissionOut,
    NodeCreate,
    NodeUpdate,
    SensorCreate,
    SensorUpdate,
    ZoneCreate,
    ZoneUpdate,
)
from app.security import generate_token, hash_token
from app.services import audit
from app.services.common import apply_changes, commit_or_conflict, get_in_facility

# --- Зони --------------------------------------------------------------------


def list_zones(db: Session, facility: Facility) -> list[Zone]:
    """Усі зони об'єкта за назвою."""
    stmt = select(Zone).where(Zone.facility_id == facility.id).order_by(Zone.name)
    return list(db.scalars(stmt))


def create_zone(db: Session, facility: Facility, data: ZoneCreate) -> Zone:
    """Створює зону; назва унікальна в межах об'єкта."""
    zone = Zone(facility_id=facility.id, **data.model_dump())
    db.add(zone)
    commit_or_conflict(db)
    return zone


def update_zone(
    db: Session, facility: Facility, zone_id: uuid.UUID, data: ZoneUpdate
) -> Zone:
    """Змінює назву або тип зони."""
    zone = get_in_facility(db, Zone, zone_id, facility.id)
    apply_changes(zone, data)
    commit_or_conflict(db)
    return zone


def delete_zone(db: Session, facility: Facility, zone_id: uuid.UUID) -> None:
    """Видаляє зону, якщо до неї не прив'язано датчиків."""
    zone = get_in_facility(db, Zone, zone_id, facility.id)
    db.delete(zone)
    commit_or_conflict(db, "in_use")


# --- Вузли -------------------------------------------------------------------


def list_nodes(db: Session, facility: Facility) -> list[Node]:
    """Усі вузли об'єкта."""
    stmt = (
        select(Node)
        .where(Node.facility_id == facility.id)
        .order_by(Node.created_at, Node.id)
    )
    return list(db.scalars(stmt))


def get_node(db: Session, facility: Facility, node_id: uuid.UUID) -> Node:
    """Вузол об'єкта за ідентифікатором."""
    return get_in_facility(db, Node, node_id, facility.id)


def create_node(db: Session, facility: Facility, data: NodeCreate) -> Node:
    """Реєструє вузол; серійний номер унікальний у системі."""
    node = Node(facility_id=facility.id, **data.model_dump())
    db.add(node)
    commit_or_conflict(db)
    return node


def update_node(
    db: Session, facility: Facility, node_id: uuid.UUID, data: NodeUpdate
) -> Node:
    """Змінює назву вузла."""
    node = get_node(db, facility, node_id)
    apply_changes(node, data)
    db.commit()
    return node


def delete_node(db: Session, facility: Facility, node_id: uuid.UUID) -> None:
    """Видаляє вузол разом із датчиками та подіями."""
    node = get_node(db, facility, node_id)
    db.delete(node)
    db.commit()


def commission_node(
    db: Session, facility: Facility, actor: User, node_id: uuid.UUID
) -> NodeCommissionOut:
    """Введення вузла в експлуатацію: видає новий токен пристрою.

    Токен повертається лише один раз, у БД зберігається його хеш.
    Повторне введення в експлуатацію робить попередній токен недійсним.
    Вузол стає online після першого службового повідомлення.
    """
    node = get_node(db, facility, node_id)
    token = generate_token()
    node.device_token_hash = hash_token(token)
    node.commissioned_at = datetime.now(UTC)
    node.status = NodeStatus.PROVISIONING
    audit.record(db, actor.id, "node.commission", "node", node.id)
    db.commit()
    return NodeCommissionOut(
        node_id=node.id, device_token=token, commissioned_at=node.commissioned_at
    )


# --- Датчики -----------------------------------------------------------------


def list_sensors(db: Session, facility: Facility, node_id: uuid.UUID) -> list[Sensor]:
    """Датчики вузла за номером каналу."""
    node = get_node(db, facility, node_id)
    stmt = select(Sensor).where(Sensor.node_id == node.id).order_by(Sensor.channel)
    return list(db.scalars(stmt))


def create_sensor(
    db: Session, facility: Facility, node_id: uuid.UUID, data: SensorCreate
) -> Sensor:
    """Додає датчик на вільний канал вузла й прив'язує його до зони."""
    node = get_node(db, facility, node_id)
    _check_zone(db, facility, data.zone_id)
    sensor = Sensor(node_id=node.id, **data.model_dump())
    db.add(sensor)
    commit_or_conflict(db)
    return sensor


def update_sensor(
    db: Session,
    facility: Facility,
    node_id: uuid.UUID,
    sensor_id: uuid.UUID,
    data: SensorUpdate,
) -> Sensor:
    """Змінює назву, зону або вмикає/вимикає датчик."""
    sensor = _get_sensor(db, facility, node_id, sensor_id)
    if data.zone_id is not None:
        _check_zone(db, facility, data.zone_id)
    apply_changes(sensor, data)
    db.commit()
    return sensor


def delete_sensor(
    db: Session, facility: Facility, node_id: uuid.UUID, sensor_id: uuid.UUID
) -> None:
    """Видаляє датчик (у подіях посилання на нього стає порожнім)."""
    sensor = _get_sensor(db, facility, node_id, sensor_id)
    db.delete(sensor)
    db.commit()


def _get_sensor(
    db: Session, facility: Facility, node_id: uuid.UUID, sensor_id: uuid.UUID
) -> Sensor:
    node = get_node(db, facility, node_id)
    sensor = db.get(Sensor, sensor_id)
    if sensor is None or sensor.node_id != node.id:
        raise NotFoundError()
    return sensor


def _check_zone(db: Session, facility: Facility, zone_id: uuid.UUID) -> None:
    zone = db.get(Zone, zone_id)
    if zone is None or zone.facility_id != facility.id:
        raise BadRequestError("zone_mismatch")
