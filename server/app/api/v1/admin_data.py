"""Маршрути адміністрування даних: статистика, очищення, резервні копії."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, status
from fastapi.responses import FileResponse

from app.config import settings
from app.deps import AdminUser, DbSession, Paging
from app.pagination import page_response
from app.schemas.admin import (
    BackupCreate,
    BackupOut,
    ConfirmedAction,
    PurgeResult,
    RestoreResult,
    SystemStats,
)
from app.schemas.common import Page
from app.services import admin as admin_service
from app.services import backup as backup_service
from app.services.reauth import confirm_action
from app.services.retention import purge_expired_data

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
def stats(admin: AdminUser, db: DbSession) -> SystemStats:
    """Кількість користувачів, об'єктів, вузлів, подій і розмір архіву."""
    return SystemStats(**admin_service.system_stats(db, admin))


@router.post("/data/purge")
def purge(data: ConfirmedAction, admin: AdminUser, db: DbSession) -> PurgeResult:
    """Видалення подій і тривог, старших за строк зберігання тарифу."""
    confirm_action(admin, data.confirmation)
    report = purge_expired_data(db, datetime.now(UTC), admin.id)
    return PurgeResult(alarms=report.alarms, events=report.events)


@router.post("/backups", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
def create_backup(data: BackupCreate, admin: AdminUser, db: DbSession) -> object:
    """Створення резервної копії (JSON, gzip) у каталозі BACKUP_DIR."""
    return backup_service.create_backup(db, admin, data.kind, settings.backup_dir)


@router.get("/backups", response_model=Page[BackupOut])
def list_backups(admin: AdminUser, db: DbSession, paging: Paging) -> object:
    """Реєстр резервних копій."""
    return page_response(backup_service.list_backups(db, paging), paging)


@router.get("/backups/{backup_id}/download", response_class=FileResponse)
def download_backup(
    backup_id: uuid.UUID, admin: AdminUser, db: DbSession
) -> FileResponse:
    """Завантаження файлу копії."""
    path = backup_service.backup_path(db, admin, backup_id, settings.backup_dir)
    return FileResponse(path, media_type="application/gzip", filename=path.name)


@router.post("/backups/{backup_id}/restore")
def restore_backup(
    backup_id: uuid.UUID, data: ConfirmedAction, admin: AdminUser, db: DbSession
) -> RestoreResult:
    """Відновлення з копії в одній транзакції (потрібне підтвердження)."""
    confirm_action(admin, data.confirmation)
    report = backup_service.restore_backup(db, admin, backup_id, settings.backup_dir)
    return RestoreResult(kind=report.kind, rows=report.rows)


@router.delete("/backups/{backup_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backup(
    backup_id: uuid.UUID, data: ConfirmedAction, admin: AdminUser, db: DbSession
) -> None:
    """Видалення копії (потрібне підтвердження)."""
    confirm_action(admin, data.confirmation)
    backup_service.delete_backup(db, admin, backup_id, settings.backup_dir)
