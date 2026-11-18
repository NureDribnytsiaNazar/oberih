"""Контроль доступності IoT-вузлів (ФМ-4, СЧ-4).

Вузол недоступний, якщо now − last_seen > T(опит.) × N(проп.)
(за замовчуванням 30 с × 3 = 90 с). Подія node_offline або node_online
створюється один раз на кожен перехід стану.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.devices import Node
from app.models.enums import EventType, NodeStatus
from app.models.events import Event
from app.models.facilities import FacilitySettings


def mark_seen(db: Session, node: Node, now: datetime | None = None) -> None:
    """Вузол на зв'язку: оновлює час і повертає статус online.

    Якщо вузол був недоступний, архівується подія node_online.
    """
    now = now or datetime.now(UTC)
    if node.status == NodeStatus.OFFLINE:
        _add_node_event(db, node, EventType.NODE_ONLINE, now)
    node.last_seen_at = now
    node.status = NodeStatus.ONLINE


def offline_deadline(settings: FacilitySettings) -> timedelta:
    """Допустимий час без зв'язку: T(опит.) × N(проп.)."""
    return timedelta(seconds=settings.poll_interval_s * settings.missed_polls_limit)


def detect_offline(db: Session, now: datetime) -> int:
    """Позначає недоступними вузли без зв'язку довше допустимого.

    Обробляються лише вузли зі статусом online, тому повторного запису
    події node_offline для вже недоступного вузла не буде.
    """
    rows = db.execute(
        select(Node, FacilitySettings)
        .join(FacilitySettings, FacilitySettings.facility_id == Node.facility_id)
        .where(Node.status == NodeStatus.ONLINE, Node.last_seen_at.is_not(None))
    ).all()
    count = 0
    for node, settings in rows:
        last_seen = node.last_seen_at
        if last_seen is not None and now - last_seen > offline_deadline(settings):
            node.status = NodeStatus.OFFLINE
            _add_node_event(db, node, EventType.NODE_OFFLINE, now)
            count += 1
    return count


def _add_node_event(
    db: Session, node: Node, event_type: EventType, now: datetime
) -> None:
    """Службова подія вузла (без датчика й порядкового номера)."""
    db.add(
        Event(
            facility_id=node.facility_id,
            node_id=node.id,
            event_type=event_type,
            occurred_at=now,
            received_at=now,
        )
    )
