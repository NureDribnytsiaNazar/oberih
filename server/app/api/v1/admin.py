"""Маршрути адміністрування платформи та довідник тарифів."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import AdminUser, DbSession, Paging
from app.pagination import page_response
from app.schemas.admin import (
    AdminUserOut,
    AuditLogOut,
    PlatformAdminUpdate,
    SessionsRevoked,
    TariffUpdate,
)
from app.schemas.common import Page
from app.schemas.users import TariffOut
from app.services import admin as service
from app.services import admin_users

router = APIRouter(tags=["admin"])


@router.get("/admin/users", response_model=Page[AdminUserOut])
def list_users(admin: AdminUser, db: DbSession, paging: Paging) -> object:
    """Усі користувачі платформи (лише адміністратор)."""
    return page_response(service.list_users(db, admin, paging), paging)


@router.get("/admin/audit-log", response_model=Page[AuditLogOut])
def audit_log(
    admin: AdminUser,
    db: DbSession,
    paging: Paging,
    user_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
) -> object:
    """Журнал аудиту з фільтрами (лише адміністратор)."""
    page = service.list_audit_log(db, paging, user_id, action, entity_type)
    return page_response(page, paging)


@router.get("/tariffs", response_model=list[TariffOut])
def list_tariffs(db: DbSession) -> object:
    """Тарифні плани (доступно без автентифікації)."""
    return service.list_tariffs(db)


@router.get("/admin/users/{user_id}", response_model=AdminUserOut)
def get_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> object:
    """Обліковий запис користувача."""
    return admin_users.get_user(db, admin, user_id)


@router.post("/admin/users/{user_id}/block", response_model=AdminUserOut)
def block_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> object:
    """Блокування: вхід заборонено, сесії завершуються."""
    return admin_users.block(db, admin, user_id)


@router.post("/admin/users/{user_id}/unblock", response_model=AdminUserOut)
def unblock_user(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> object:
    """Розблокування."""
    return admin_users.unblock(db, admin, user_id)


@router.put("/admin/users/{user_id}/platform-admin", response_model=AdminUserOut)
def set_platform_admin(
    user_id: uuid.UUID, data: PlatformAdminUpdate, admin: AdminUser, db: DbSession
) -> object:
    """Надання або зняття прав адміністратора (крім останнього)."""
    return admin_users.set_platform_admin(db, admin, user_id, data.is_platform_admin)


@router.post("/admin/users/{user_id}/sessions/revoke")
def revoke_sessions(
    user_id: uuid.UUID, admin: AdminUser, db: DbSession
) -> SessionsRevoked:
    """Примусове завершення всіх сесій користувача."""
    return SessionsRevoked(revoked=admin_users.revoke_sessions(db, admin, user_id))


@router.post("/admin/users/{user_id}/totp/reset", response_model=AdminUserOut)
def reset_totp(user_id: uuid.UUID, admin: AdminUser, db: DbSession) -> object:
    """Скидання двофакторної автентифікації."""
    return admin_users.reset_totp(db, admin, user_id)


@router.put("/admin/users/{user_id}/tariff", response_model=AdminUserOut)
def set_tariff(
    user_id: uuid.UUID, data: TariffUpdate, admin: AdminUser, db: DbSession
) -> object:
    """Зміна тарифного плану."""
    return admin_users.set_tariff(db, admin, user_id, data.code)
