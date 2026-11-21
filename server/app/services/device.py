"""Приймання подій і службових повідомлень від IoT-вузлів (ФМ-2).

Обробка подій виконується конвеєром (pipeline/processor.py); тут лише
точки входу для маршрутів пристрою.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.devices import Node
from app.models.facilities import Facility
from app.schemas.events import (
    DeviceEventBatch,
    DeviceEventsResult,
    HeartbeatIn,
    HeartbeatOut,
)
from app.services import arming, commands, nodes
from app.services.pipeline.processor import ingest_batch


def ingest_events(
    db: Session, node: Node, batch: DeviceEventBatch
) -> DeviceEventsResult:
    """Пакет подій вузла; повторні події позначаються як duplicate."""
    return ingest_batch(db, node, batch)


def heartbeat(
    db: Session, node: Node, data: HeartbeatIn, now: datetime | None = None
) -> HeartbeatOut:
    """Службове повідомлення: вузол на зв'язку.

    Порядок: підтвердження отриманих команд, узгодження режиму, видача
    відкритих команд і поточної конфігурації вузла.
    """
    now = now or datetime.now(UTC)
    nodes.mark_seen(db, node, now)
    if data.firmware_version:
        node.firmware_version = data.firmware_version
    facility = db.get_one(Facility, node.facility_id)
    arming.apply_due_timer(db, facility, now)
    commands.acknowledge(db, node, data.acked_command_ids, now)
    report = commands.NodeReport(mode=data.mode, buffer_depth=data.buffer_depth)
    commands.reconcile_mode(db, node, facility, report, now)
    pending = commands.deliver(db, node, now)
    config = commands.node_config(node, facility.settings)
    db.commit()
    return HeartbeatOut(
        server_time=now,
        poll_interval_s=facility.settings.poll_interval_s,
        facility_mode=facility.mode,
        server_epoch=int(now.timestamp()),
        commands=pending,
        config=config,
    )
