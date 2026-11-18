"""Резервні копії: логічний дамп БД у JSON (gzip) і відновлення (СЧ-9).

Копія не залежить від pg_dump і переноситься між серверами. У заголовку
файлу є format_version. Повна копія містить усі дані, крім сесій
(refresh_tokens) і самого реєстру копій; копія налаштувань — лише
налаштування об'єктів без токенів пристроїв. Приватних ключів у БД немає,
тому в копію вони не потрапляють.
"""

import enum
import gzip
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Numeric,
    Table,
    Time,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.errors import AppError, BadRequestError, ConflictError, NotFoundError
from app.models import Base
from app.models.admin import Backup
from app.models.enums import BackupKind, BackupStatus
from app.models.users import User
from app.pagination import PageParams, paginate
from app.services import audit

FORMAT_VERSION = 1
EXCLUDED_TABLES = frozenset({"refresh_tokens", "backups"})
# Таблиці копії налаштувань у порядку залежностей (для вставки).
SETTINGS_TABLES = (
    "tariff_plans",
    "facilities",
    "facility_settings",
    "zones",
    "schedules",
    "nodes",
    "sensors",
    "test_scenarios",
)
# Стовпці, що не потрапляють у копію налаштувань і не перезаписуються.
SETTINGS_SECRET_COLUMNS = {"nodes": frozenset({"device_token_hash"})}


@dataclass(frozen=True)
class RestoreReport:
    """Кількість відновлених рядків за таблицями."""

    kind: BackupKind
    rows: dict[str, int]


# --- Створення ---------------------------------------------------------------


def create_backup(
    db: Session, admin: User, kind: BackupKind, backup_dir: Path
) -> Backup:
    """Створює файл копії та запис про нього (sha256, розмір, статус)."""
    now = datetime.now(UTC)
    suffix = uuid.uuid4().hex[:8]
    record = Backup(
        created_by=admin.id,
        kind=kind,
        status=BackupStatus.PENDING,
        file_name=f"oberih-{kind.value}-{now:%Y%m%d-%H%M%S}-{suffix}.json.gz",
    )
    db.add(record)
    db.flush()
    payload = {
        "format_version": FORMAT_VERSION,
        "kind": kind.value,
        "created_at": now.isoformat(),
        "tables": {table.name: _dump_table(db, table, kind) for table in _tables(kind)},
    }
    data = gzip.compress(
        json.dumps(payload, ensure_ascii=False, default=_encode).encode("utf-8")
    )
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        (backup_dir / record.file_name).write_bytes(data)
    except OSError:
        record.status = BackupStatus.FAILED
        db.commit()
        raise AppError(500, "backup_failed")
    record.size_bytes = len(data)
    record.sha256 = hashlib.sha256(data).hexdigest()
    record.status = BackupStatus.COMPLETED
    audit.record(
        db, admin.id, "backup.create", "backup", record.id, {"kind": kind.value}
    )
    db.commit()
    return record


# --- Відновлення -------------------------------------------------------------


def restore_backup(
    db: Session, admin: User, backup_id: uuid.UUID, backup_dir: Path
) -> RestoreReport:
    """Відновлює дані з копії в одній транзакції.

    Перевіряються контрольна сума й версія формату. Будь-яка помилка під
    час вставки відкочує транзакцію повністю: часткових даних не лишається.
    """
    record = get_backup(db, backup_id)
    payload = _read_verified(record, backup_dir)
    kind = BackupKind(payload["kind"])
    admin_id = admin.id
    try:
        if kind == BackupKind.FULL:
            rows = _restore_full(db, payload["tables"])
        else:
            rows = _restore_settings(db, payload["tables"])
        # Після повного відновлення адміністратора може не бути серед користувачів.
        actor = admin_id if db.get(User, admin_id) is not None else None
        audit.record(
            db, actor, "backup.restore", "backup", record.id, {"kind": kind.value}
        )
        db.commit()
    except (SQLAlchemyError, KeyError, ValueError, TypeError):
        db.rollback()
        raise BadRequestError("backup_restore_failed")
    return RestoreReport(kind, rows)


def _read_verified(record: Backup, backup_dir: Path) -> dict[str, Any]:
    if record.status != BackupStatus.COMPLETED:
        raise ConflictError("backup_not_ready")
    path = backup_dir / record.file_name
    if not path.exists():
        raise NotFoundError("backup_file_missing")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record.sha256:
        raise BadRequestError("backup_corrupted")
    try:
        payload: dict[str, Any] = json.loads(gzip.decompress(data).decode("utf-8"))
    except (OSError, ValueError):
        raise BadRequestError("backup_corrupted")
    if payload.get("format_version") != FORMAT_VERSION:
        raise BadRequestError("backup_unsupported_format")
    return payload


def _restore_full(
    db: Session, tables: dict[str, list[dict[str, Any]]]
) -> dict[str, int]:
    """Повна заміна даних: TRUNCATE (не зачіпає тригери рядків) і вставка."""
    targets = _tables(BackupKind.FULL)
    names = ", ".join(table.name for table in targets)
    db.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    counts = {}
    for table in targets:
        rows = [_decode_row(table, row) for row in tables.get(table.name, [])]
        if rows:
            db.execute(table.insert(), rows)
        _reset_identity(db, table)
        counts[table.name] = len(rows)
    return counts


def _restore_settings(
    db: Session, tables: dict[str, list[dict[str, Any]]]
) -> dict[str, int]:
    """Оновлює або додає налаштування за первинним ключем (ідемпотентно)."""
    counts = {}
    for table in _tables(BackupKind.SETTINGS):
        rows = [_decode_row(table, row) for row in tables.get(table.name, [])]
        keys = [column.name for column in table.primary_key.columns]
        for row in rows:
            updates = {
                name: value
                for name, value in row.items()
                if name not in keys
                and name not in SETTINGS_SECRET_COLUMNS.get(table.name, ())
            }
            stmt = insert(table).values(row)
            db.execute(
                stmt.on_conflict_do_update(index_elements=keys, set_=updates)
                if updates
                else stmt.on_conflict_do_nothing()
            )
        counts[table.name] = len(rows)
    return counts


# --- Реєстр копій ------------------------------------------------------------


def list_backups(db: Session, params: PageParams) -> tuple[list[Backup], int]:
    """Усі копії, найновіші першими."""
    stmt = select(Backup).order_by(Backup.created_at.desc(), Backup.id)
    return paginate(db, stmt, params)


def get_backup(db: Session, backup_id: uuid.UUID) -> Backup:
    """Запис про копію."""
    record = db.get(Backup, backup_id)
    if record is None:
        raise NotFoundError()
    return record


def backup_path(
    db: Session, admin: User, backup_id: uuid.UUID, backup_dir: Path
) -> Path:
    """Шлях до файлу копії для завантаження (фіксується в аудиті)."""
    record = get_backup(db, backup_id)
    path = backup_dir / record.file_name
    if record.status != BackupStatus.COMPLETED or not path.exists():
        raise NotFoundError("backup_file_missing")
    audit.record(db, admin.id, "backup.download", "backup", record.id)
    db.commit()
    return path


def delete_backup(
    db: Session, admin: User, backup_id: uuid.UUID, backup_dir: Path
) -> None:
    """Видаляє файл і запис про копію."""
    record = get_backup(db, backup_id)
    (backup_dir / record.file_name).unlink(missing_ok=True)
    db.delete(record)
    audit.record(db, admin.id, "backup.delete", "backup", backup_id)
    db.commit()


# --- Перетворення значень ----------------------------------------------------


def _tables(kind: BackupKind) -> list[Table]:
    """Таблиці копії в порядку залежностей зовнішніх ключів."""
    if kind == BackupKind.SETTINGS:
        return [Base.metadata.tables[name] for name in SETTINGS_TABLES]
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


def _dump_table(db: Session, table: Table, kind: BackupKind) -> list[dict[str, Any]]:
    hidden = SETTINGS_SECRET_COLUMNS.get(table.name, frozenset())
    columns = [
        column
        for column in table.columns
        if kind == BackupKind.FULL or column.name not in hidden
    ]
    keys = list(table.primary_key.columns)
    rows = db.execute(select(*columns).order_by(*keys)).mappings()
    return [dict(row) for row in rows]


def _encode(value: Any) -> Any:
    """Перетворює значення, яких немає в JSON, на рядки."""
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    raise TypeError(f"Unsupported value type: {type(value).__name__}")


def _decode_row(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    """Відновлює типи значень рядка за типами стовпців таблиці."""
    return {
        name: _decode(table.columns[name].type, value)
        for name, value in row.items()
        if name in table.columns
    }


def _decode(column_type: Any, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column_type, Uuid):
        return uuid.UUID(value)
    if isinstance(column_type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column_type, Date):
        return date.fromisoformat(value)
    if isinstance(column_type, Time):
        return time.fromisoformat(value)
    if isinstance(column_type, Enum) and column_type.enum_class is not None:
        return column_type.enum_class(value)
    if isinstance(column_type, Numeric):
        return Decimal(value)
    return value


def _reset_identity(db: Session, table: Table) -> None:
    """Після вставки з явними id лічильник Identity продовжує з максимуму."""
    identity = next((c for c in table.columns if c.identity is not None), None)
    if identity is None:
        return
    max_id = db.scalar(select(func.max(identity)))
    sequence = func.pg_get_serial_sequence(table.name, identity.name)
    db.execute(select(func.setval(sequence, max_id or 1, max_id is not None)))
