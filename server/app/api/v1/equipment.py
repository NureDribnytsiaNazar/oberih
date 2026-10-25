"""Маршрути зон, IoT-вузлів і датчиків об'єкта."""

import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.facilities import (
    NodeCommissionOut,
    NodeCreate,
    NodeOut,
    NodeUpdate,
    SensorCreate,
    SensorOut,
    SensorUpdate,
    ZoneCreate,
    ZoneOut,
    ZoneUpdate,
)
from app.services import equipment as service
from app.services.access import Permission, require_access

router = APIRouter(prefix="/facilities/{facility_id}", tags=["equipment"])

# --- Зони --------------------------------------------------------------------


@router.get("/zones", response_model=list[ZoneOut])
def list_zones(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> object:
    """Зони об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return service.list_zones(db, facility)


@router.post("/zones", response_model=ZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(
    facility_id: uuid.UUID, data: ZoneCreate, user: CurrentUser, db: DbSession
) -> object:
    """Створення зони (власник, монтажник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.create_zone(db, facility, data)


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
def update_zone(
    facility_id: uuid.UUID,
    zone_id: uuid.UUID,
    data: ZoneUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна зони."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.update_zone(db, facility, zone_id, data)


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(
    facility_id: uuid.UUID, zone_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Видалення зони без датчиків."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    service.delete_zone(db, facility, zone_id)


# --- Вузли -------------------------------------------------------------------


@router.get("/nodes", response_model=list[NodeOut])
def list_nodes(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> object:
    """Вузли об'єкта та стан їхнього зв'язку."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return service.list_nodes(db, facility)


@router.post("/nodes", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
def create_node(
    facility_id: uuid.UUID, data: NodeCreate, user: CurrentUser, db: DbSession
) -> object:
    """Реєстрація вузла за серійним номером."""
    facility, _ = require_access(db, facility_id, user, Permission.COMMISSION_NODE)
    return service.create_node(db, facility, data)


@router.get("/nodes/{node_id}", response_model=NodeOut)
def get_node(
    facility_id: uuid.UUID, node_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> object:
    """Вузол об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return service.get_node(db, facility, node_id)


@router.patch("/nodes/{node_id}", response_model=NodeOut)
def update_node(
    facility_id: uuid.UUID,
    node_id: uuid.UUID,
    data: NodeUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна назви вузла."""
    facility, _ = require_access(db, facility_id, user, Permission.COMMISSION_NODE)
    return service.update_node(db, facility, node_id, data)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(
    facility_id: uuid.UUID, node_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Видалення вузла разом із датчиками."""
    facility, _ = require_access(db, facility_id, user, Permission.COMMISSION_NODE)
    service.delete_node(db, facility, node_id)


@router.post("/nodes/{node_id}/commission")
def commission_node(
    facility_id: uuid.UUID, node_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> NodeCommissionOut:
    """Введення в експлуатацію: токен пристрою показується лише один раз."""
    facility, _ = require_access(db, facility_id, user, Permission.COMMISSION_NODE)
    return service.commission_node(db, facility, user, node_id)


# --- Датчики -----------------------------------------------------------------


@router.get("/nodes/{node_id}/sensors", response_model=list[SensorOut])
def list_sensors(
    facility_id: uuid.UUID, node_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> object:
    """Датчики вузла."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return service.list_sensors(db, facility, node_id)


@router.post(
    "/nodes/{node_id}/sensors",
    response_model=SensorOut,
    status_code=status.HTTP_201_CREATED,
)
def create_sensor(
    facility_id: uuid.UUID,
    node_id: uuid.UUID,
    data: SensorCreate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Додавання датчика на канал вузла."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.create_sensor(db, facility, node_id, data)


@router.patch("/nodes/{node_id}/sensors/{sensor_id}", response_model=SensorOut)
def update_sensor(
    facility_id: uuid.UUID,
    node_id: uuid.UUID,
    sensor_id: uuid.UUID,
    data: SensorUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна датчика."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return service.update_sensor(db, facility, node_id, sensor_id, data)


@router.delete(
    "/nodes/{node_id}/sensors/{sensor_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_sensor(
    facility_id: uuid.UUID,
    node_id: uuid.UUID,
    sensor_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> None:
    """Видалення датчика."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    service.delete_sensor(db, facility, node_id, sensor_id)
