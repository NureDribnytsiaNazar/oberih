"""Черга підписаних команд для IoT-вузлів (ІК-7) і конфігурація вузла (ІК-8).

Сервер — джерело істини для режиму охорони. Команди потрапляють у чергу
після дій користувача (arm, disarm, зміна налаштувань) і видаються вузлу
у відповіді heartbeat, доки той не підтвердить їх або не мине строк дії.

Підпис: HMAC-SHA256(command_key,
"<node_id>|<nonce>|<command_type>|<canonical_payload>|<issued_at>"),
де issued_at — секунди Unix, а canonical_payload — JSON без пробілів із
ключами за абеткою. Одноразове число строго зростає в межах вузла.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.devices import Node, NodeCommand
from app.models.enums import CommandStatus, CommandType, FacilityMode
from app.models.facilities import Facility, FacilitySettings
from app.schemas.events import NodeCommandOut, NodeConfigOut

COMMAND_TTL = timedelta(seconds=60)
# Якщо вузол отримав таку саму команду узгодження нещодавно, але стан не
# змінився (наприклад, вузол відхиляє підпис), повтор не створюється.
RECONCILE_RETRY = timedelta(minutes=5)
COMMAND_KEY_BYTES = 32

# Режим сервера -> команда, що приводить до нього вузол. Затримку входу й
# тривогу вузол формує сам за подіями датчиків, тому їх не узгоджуємо.
MODE_COMMANDS: dict[FacilityMode, CommandType] = {
    FacilityMode.DISARMED: CommandType.DISARM,
    FacilityMode.ARMED_HOME: CommandType.ARM_HOME,
    FacilityMode.EXIT_DELAY: CommandType.ARM_AWAY,
    FacilityMode.ARMED_AWAY: CommandType.ARM_AWAY,
}
# Режими вузла, які вважаються узгодженими з режимом сервера.
EQUIVALENT_MODES: dict[FacilityMode, frozenset[FacilityMode]] = {
    FacilityMode.DISARMED: frozenset({FacilityMode.DISARMED}),
    FacilityMode.ARMED_HOME: frozenset({FacilityMode.ARMED_HOME}),
    FacilityMode.EXIT_DELAY: frozenset(
        {FacilityMode.EXIT_DELAY, FacilityMode.ARMED_AWAY}
    ),
    FacilityMode.ARMED_AWAY: frozenset(
        {FacilityMode.EXIT_DELAY, FacilityMode.ARMED_AWAY}
    ),
}
OPEN_STATUSES = (CommandStatus.PENDING, CommandStatus.DELIVERED)


@dataclass(frozen=True)
class NodeReport:
    """Стан вузла з heartbeat, потрібний для узгодження режиму."""

    mode: FacilityMode | None
    buffer_depth: int | None


# --- Підпис ------------------------------------------------------------------


def new_command_key() -> bytes:
    """Випадковий ключ підпису команд для вузла."""
    return secrets.token_bytes(COMMAND_KEY_BYTES)


def canonical_payload(payload: dict[str, Any]) -> str:
    """Канонічний JSON: без пробілів, ключі за абеткою."""
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def signing_string(command: NodeCommand) -> str:
    """Рядок, над яким обчислюється підпис команди."""
    return "|".join(
        (
            str(command.node_id),
            str(command.nonce),
            command.command_type.value,
            canonical_payload(command.payload),
            str(_epoch(command.issued_at)),
        )
    )


def sign(key: bytes, message: str) -> str:
    """HMAC-SHA256 у шістнадцятковому вигляді."""
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify(key: bytes, message: str, signature: str) -> bool:
    """Перевірка підпису з порівнянням сталого часу (як на вузлі)."""
    return hmac.compare_digest(sign(key, message), signature)


# --- Черга -------------------------------------------------------------------


def enqueue(
    db: Session,
    node: Node,
    command_type: CommandType,
    payload: dict[str, Any],
    now: datetime | None = None,
) -> NodeCommand | None:
    """Додає команду в чергу вузла; без ключа підпису команда не створюється.

    Одноразове число — більше з (останнє + 1) і поточного часу в мс: так
    воно зростає навіть після очищення БД, а вузол зберігає останнє у NVS.
    """
    if node.command_key is None:
        return None
    now = now or datetime.now(UTC)
    # Блокування рядка вузла: паралельні запити (дія користувача й heartbeat)
    # обчислюють nonce по черзі й не порушують унікальність (node_id, nonce).
    db.execute(select(Node.id).where(Node.id == node.id).with_for_update())
    last = db.scalar(
        select(func.max(NodeCommand.nonce)).where(NodeCommand.node_id == node.id)
    )
    nonce = max((last or 0) + 1, int(now.timestamp() * 1000))
    command = NodeCommand(
        node_id=node.id,
        command_type=command_type,
        payload=payload,
        nonce=nonce,
        issued_at=now.replace(microsecond=0),
        expires_at=now.replace(microsecond=0) + COMMAND_TTL,
        status=CommandStatus.PENDING,
    )
    db.add(command)
    db.flush()
    return command


def enqueue_mode(
    db: Session, facility: Facility, now: datetime | None = None
) -> list[NodeCommand]:
    """Ставить усім вузлам об'єкта команду, що відповідає його режиму."""
    command_type = MODE_COMMANDS.get(facility.mode)
    if command_type is None:
        return []
    payload = {"mode": facility.mode.value}
    created = [
        enqueue(db, node, command_type, payload, now)
        for node in _facility_nodes(db, facility)
    ]
    return [command for command in created if command is not None]


def config_changed(
    db: Session, facility: Facility, nodes: list[Node] | None = None
) -> None:
    """Збільшує версію конфігурації й ставить команду set_config.

    Без списку nodes зміна стосується всіх вузлів об'єкта (змінено
    налаштування об'єкта: затримки чи інтервал опитування).
    """
    if nodes is None:
        nodes = list(db.scalars(select(Node).where(Node.facility_id == facility.id)))
    for node in nodes:
        node.config_version += 1
        config = node_config(node, facility.settings)
        enqueue(db, node, CommandType.SET_CONFIG, config.model_dump())


def renew_config_version(node: Node, now: datetime) -> None:
    """Версія конфігурації після (повторного) введення вузла в експлуатацію.

    Не менша за поточний час Unix: після очищення чи відновлення БД сервера
    вузол, що зберігає в NVS більшу стару версію, знову приймає конфігурацію.
    """
    node.config_version = max(node.config_version + 1, int(now.timestamp()))


def node_config(node: Node, settings: FacilitySettings) -> NodeConfigOut:
    """Повна конфігурація вузла: параметри об'єкта й самого вузла."""
    return NodeConfigOut(
        exit_delay_s=settings.exit_delay_s,
        entry_delay_s=settings.entry_delay_s,
        poll_interval_s=settings.poll_interval_s,
        debounce_ms=node.debounce_ms,
        pir_lockout_s=node.pir_lockout_s,
        config_version=node.config_version,
    )


# --- Обмін із вузлом під час heartbeat ---------------------------------------


def acknowledge(db: Session, node: Node, command_ids: list[Any], now: datetime) -> int:
    """Позначає підтверджені команди. Чужі ідентифікатори ігноруються."""
    if not command_ids:
        return 0
    result = db.execute(
        update(NodeCommand)
        .where(
            NodeCommand.node_id == node.id,
            NodeCommand.id.in_(command_ids),
            NodeCommand.acked_at.is_(None),
        )
        .values(acked_at=now, status=CommandStatus.ACKED)
    )
    return int(getattr(result, "rowcount", 0) or 0)


def reconcile_mode(
    db: Session, node: Node, facility: Facility, report: NodeReport, now: datetime
) -> NodeCommand | None:
    """Узгодження режиму після автономної роботи (сервер — джерело істини).

    Команду створюємо, лише якщо вузол повідомив режим, у його буфері
    немає ненадісланих подій (інакше розбіжність — це ще не доставлена
    тривога) і для вузла немає відкритої команди.
    """
    expected = EQUIVALENT_MODES.get(facility.mode)
    if report.mode is None or expected is None or report.mode in expected:
        return None
    if report.buffer_depth:
        return None
    if _open_commands(db, node, now):
        return None
    command_type = MODE_COMMANDS[facility.mode]
    payload = {"mode": facility.mode.value}
    if _recently_sent(db, node, command_type, payload, now):
        return None
    return enqueue(db, node, command_type, payload, now)


def reconcile_config(
    db: Session,
    node: Node,
    facility: Facility,
    reported_version: int | None,
    now: datetime,
) -> NodeCommand | None:
    """Повторна підписана set_config для вузла з застарілою конфігурацією.

    Вузол застосовує конфігурацію лише з підписаної команди (ІК-7), тому,
    якщо він пропустив set_config (строк дії минув, NVS очищено), сервер
    надсилає її знову за версією з heartbeat.
    """
    if reported_version is None or reported_version >= node.config_version:
        return None
    if any(
        command.command_type == CommandType.SET_CONFIG
        for command in _open_commands(db, node, now)
    ):
        return None
    payload = node_config(node, facility.settings).model_dump()
    if _recently_sent(db, node, CommandType.SET_CONFIG, payload, now):
        return None
    return enqueue(db, node, CommandType.SET_CONFIG, payload, now)


def deliver(db: Session, node: Node, now: datetime) -> list[NodeCommandOut]:
    """Команди для відповіді heartbeat; прострочені позначаються expired."""
    db.execute(
        update(NodeCommand)
        .where(
            NodeCommand.node_id == node.id,
            NodeCommand.status.in_(OPEN_STATUSES),
            NodeCommand.expires_at <= now,
        )
        .values(status=CommandStatus.EXPIRED)
    )
    commands = _open_commands(db, node, now)
    for command in commands:
        if command.delivered_at is None:
            command.delivered_at = now
            command.status = CommandStatus.DELIVERED
    key = node.command_key
    if key is None:
        return []
    return [_signed(command, key) for command in commands]


def list_commands(db: Session, node: Node, limit: int = 50) -> list[NodeCommand]:
    """Останні команди вузла, найновіші першими."""
    stmt = (
        select(NodeCommand)
        .where(NodeCommand.node_id == node.id)
        .order_by(NodeCommand.nonce.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def _recently_sent(
    db: Session,
    node: Node,
    command_type: CommandType,
    payload: dict[str, Any],
    now: datetime,
) -> bool:
    """Чи видавалася вузлу така сама команда протягом RECONCILE_RETRY."""
    latest = db.scalars(
        select(NodeCommand)
        .where(
            NodeCommand.node_id == node.id,
            NodeCommand.command_type == command_type,
            NodeCommand.issued_at > now - RECONCILE_RETRY,
        )
        .order_by(NodeCommand.nonce.desc())
        .limit(1)
    ).first()
    return latest is not None and latest.payload == payload


def _open_commands(db: Session, node: Node, now: datetime) -> list[NodeCommand]:
    stmt = (
        select(NodeCommand)
        .where(
            NodeCommand.node_id == node.id,
            NodeCommand.status.in_(OPEN_STATUSES),
            NodeCommand.expires_at > now,
        )
        .order_by(NodeCommand.nonce)
    )
    return list(db.scalars(stmt))


def _signed(command: NodeCommand, key: bytes) -> NodeCommandOut:
    return NodeCommandOut(
        id=command.id,
        type=command.command_type,
        payload=canonical_payload(command.payload),
        nonce=command.nonce,
        issued_at=_epoch(command.issued_at),
        expires_at=_epoch(command.expires_at),
        signature=sign(key, signing_string(command)),
    )


def _facility_nodes(db: Session, facility: Facility) -> list[Node]:
    stmt = select(Node).where(
        Node.facility_id == facility.id, Node.command_key.is_not(None)
    )
    return list(db.scalars(stmt))


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())
