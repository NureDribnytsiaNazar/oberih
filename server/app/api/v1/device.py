"""Маршрути для IoT-вузлів (автентифікація токеном пристрою)."""

from fastapi import APIRouter

from app.deps import DbSession, DeviceNode
from app.schemas.events import (
    DeviceEventBatch,
    DeviceEventsResult,
    HeartbeatIn,
    HeartbeatOut,
)
from app.services import device as service

router = APIRouter(prefix="/device", tags=["device"])


@router.post("/events")
def post_events(
    batch: DeviceEventBatch, node: DeviceNode, db: DbSession
) -> DeviceEventsResult:
    """Пакет подій вузла; повторне надсилання не створює дублікатів."""
    return service.ingest_events(db, node, batch)


@router.post("/heartbeat")
def heartbeat(data: HeartbeatIn, node: DeviceNode, db: DbSession) -> HeartbeatOut:
    """Службове повідомлення вузла (контроль доступності)."""
    return service.heartbeat(db, node, data)
