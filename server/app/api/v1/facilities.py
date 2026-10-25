"""Маршрути об'єктів, їхніх налаштувань і учасників."""

import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession, Paging
from app.pagination import page_response
from app.schemas.common import Page
from app.schemas.facilities import (
    FacilityCreate,
    FacilityOut,
    FacilitySettingsOut,
    FacilitySettingsUpdate,
    FacilityUpdate,
    MemberCreate,
    MemberOut,
    MemberUpdate,
)
from app.services import facilities as facility_service
from app.services import members as member_service
from app.services.access import Permission, require_access
from app.services.arming import finish_exit_delay

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("", response_model=Page[FacilityOut])
def list_facilities(user: CurrentUser, db: DbSession, paging: Paging) -> object:
    """Об'єкти, до яких користувач має доступ."""
    return page_response(facility_service.list_for_user(db, user, paging), paging)


@router.post("", response_model=FacilityOut, status_code=status.HTTP_201_CREATED)
def create_facility(data: FacilityCreate, user: CurrentUser, db: DbSession) -> object:
    """Створення об'єкта (кількість обмежена тарифом)."""
    return facility_service.create(db, user, data)


@router.get("/{facility_id}", response_model=FacilityOut)
def get_facility(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> object:
    """Об'єкт і його поточний режим охорони."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    finish_exit_delay(db, facility)
    return facility


@router.patch("/{facility_id}", response_model=FacilityOut)
def update_facility(
    facility_id: uuid.UUID, data: FacilityUpdate, user: CurrentUser, db: DbSession
) -> object:
    """Зміна назви, адреси, часового поясу (лише власник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_FACILITY)
    return facility_service.update(db, facility, data)


@router.delete("/{facility_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_facility(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    """Видалення об'єкта з усіма даними (лише власник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_FACILITY)
    facility_service.remove(db, user, facility)


@router.get("/{facility_id}/settings", response_model=FacilitySettingsOut)
def get_settings(facility_id: uuid.UUID, user: CurrentUser, db: DbSession) -> object:
    """Параметри бізнес-логіки: затримки, вікна, ваги, пороги."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_FACILITY)
    return facility.settings


@router.put("/{facility_id}/settings", response_model=FacilitySettingsOut)
def update_settings(
    facility_id: uuid.UUID,
    data: FacilitySettingsUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна параметрів (власник, монтажник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_ZONES)
    return facility_service.update_settings(db, facility, data)


@router.get("/{facility_id}/members", response_model=Page[MemberOut])
def list_members(
    facility_id: uuid.UUID, user: CurrentUser, db: DbSession, paging: Paging
) -> object:
    """Учасники об'єкта (лише власник)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_MEMBERS)
    return page_response(member_service.list_members(db, facility, paging), paging)


@router.post(
    "/{facility_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    facility_id: uuid.UUID, data: MemberCreate, user: CurrentUser, db: DbSession
) -> object:
    """Додавання користувача з роллю (для гостя — з терміном доступу)."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_MEMBERS)
    return member_service.add_member(db, facility, user, data)


@router.patch("/{facility_id}/members/{member_id}", response_model=MemberOut)
def update_member(
    facility_id: uuid.UUID,
    member_id: uuid.UUID,
    data: MemberUpdate,
    user: CurrentUser,
    db: DbSession,
) -> object:
    """Зміна ролі або періоду доступу учасника."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_MEMBERS)
    return member_service.update_member(db, facility, user, member_id, data)


@router.delete(
    "/{facility_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_member(
    facility_id: uuid.UUID, member_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Вилучення учасника з об'єкта."""
    facility, _ = require_access(db, facility_id, user, Permission.MANAGE_MEMBERS)
    member_service.remove_member(db, facility, user, member_id)
