"""Перевірка прав доступу до об'єкта за ролями (таблиця 7 Vision & Scope)."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ForbiddenError, NotFoundError
from app.models.enums import FacilityRole
from app.models.facilities import Facility, FacilityMember
from app.models.users import User


class Permission(str, enum.Enum):
    """Дії над об'єктом, що потребують окремого права."""

    VIEW_FACILITY = "view_facility"  # об'єкт, зони, вузли, датчики
    VIEW_EVENTS = "view_events"  # події, тривоги, журнал охорони
    ARM = "arm"  # постановка на охорону та зняття з охорони
    ACK_ALARM = "ack_alarm"  # підтвердження тривоги
    MANAGE_ZONES = "manage_zones"  # зони, правила, розклади
    COMMISSION_NODE = "commission_node"  # введення вузла в експлуатацію
    MANAGE_MEMBERS = "manage_members"  # користувачі об'єкта
    MANAGE_FACILITY = "manage_facility"  # зміна та видалення об'єкта


ROLE_PERMISSIONS: dict[FacilityRole, frozenset[Permission]] = {
    FacilityRole.OWNER: frozenset(Permission),
    FacilityRole.FAMILY: frozenset(
        {
            Permission.VIEW_FACILITY,
            Permission.VIEW_EVENTS,
            Permission.ARM,
            Permission.ACK_ALARM,
        }
    ),
    FacilityRole.GUEST: frozenset(
        {Permission.VIEW_FACILITY, Permission.VIEW_EVENTS, Permission.ARM}
    ),
    FacilityRole.INSTALLER: frozenset(
        {
            Permission.VIEW_FACILITY,
            Permission.MANAGE_ZONES,
            Permission.COMMISSION_NODE,
        }
    ),
}


def has_permission(member: FacilityMember, permission: Permission) -> bool:
    """Чи дозволяє роль учасника вказану дію."""
    return permission in ROLE_PERMISSIONS[member.role]


def is_access_active(member: FacilityMember, now: datetime | None = None) -> bool:
    """Чи діє доступ учасника зараз (обмеження часу задається гостям)."""
    now = now or datetime.now(UTC)
    if member.access_from is not None and now < member.access_from:
        return False
    if member.access_until is not None and now >= member.access_until:
        return False
    return True


def require_access(
    db: Session, facility_id: uuid.UUID, user: User, permission: Permission
) -> tuple[Facility, FacilityMember]:
    """Повертає об'єкт і членство користувача або піднімає помилку доступу.

    Якщо користувач не є учасником об'єкта, повертається 404, а не 403,
    щоб не розкривати існування чужих об'єктів.
    """
    row = db.execute(
        select(Facility, FacilityMember)
        .join(FacilityMember, FacilityMember.facility_id == Facility.id)
        .where(Facility.id == facility_id, FacilityMember.user_id == user.id)
    ).first()
    if row is None:
        raise NotFoundError()
    facility, member = row
    if not has_permission(member, permission):
        raise ForbiddenError()
    if not is_access_active(member):
        raise ForbiddenError("access_expired")
    return facility, member
