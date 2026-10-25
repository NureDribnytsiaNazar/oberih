"""Маршрути адміністрування платформи та довідник тарифів."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import AdminUser, DbSession, Paging
from app.pagination import page_response
from app.schemas.admin import AdminUserOut, AuditLogOut
from app.schemas.common import Page
from app.schemas.users import TariffOut
from app.services import admin as service

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
