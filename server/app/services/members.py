"""Учасники об'єкта: ролі та гостьовий доступ, обмежений за часом."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.enums import FacilityRole
from app.models.facilities import Facility, FacilityMember
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.facilities import MemberCreate, MemberUpdate
from app.services import audit
from app.services.common import apply_changes, get_in_facility


def list_members(
    db: Session, facility: Facility, params: PageParams
) -> tuple[list[FacilityMember], int]:
    """Учасники об'єкта; першим іде власник."""
    stmt = (
        select(FacilityMember)
        .options(joinedload(FacilityMember.user))
        .where(FacilityMember.facility_id == facility.id)
        .order_by(FacilityMember.created_at, FacilityMember.id)
    )
    return paginate(db, stmt, params)


def add_member(
    db: Session, facility: Facility, actor: User, data: MemberCreate
) -> FacilityMember:
    """Додає зареєстрованого користувача до об'єкта з указаною роллю."""
    user = db.scalar(select(User).where(User.email == data.email, User.is_active))
    if user is None:
        raise NotFoundError("user_not_found")
    exists = db.scalar(
        select(FacilityMember.id).where(
            FacilityMember.facility_id == facility.id,
            FacilityMember.user_id == user.id,
        )
    )
    if exists is not None:
        raise ConflictError("member_exists")
    _check_access_period(db, facility, data.role, data.access_from, data.access_until)

    member = FacilityMember(
        facility_id=facility.id,
        user_id=user.id,
        role=data.role,
        access_from=data.access_from,
        access_until=data.access_until,
    )
    db.add(member)
    db.flush()
    audit.record(
        db,
        actor.id,
        "member.add",
        "facility_member",
        member.id,
        {"facility_id": str(facility.id), "role": data.role.value},
    )
    db.commit()
    return member


def update_member(
    db: Session,
    facility: Facility,
    actor: User,
    member_id: uuid.UUID,
    data: MemberUpdate,
) -> FacilityMember:
    """Змінює роль або період доступу (крім власника)."""
    member = _get_editable_member(db, facility, member_id)
    apply_changes(member, data)
    _check_access_period(
        db, facility, member.role, member.access_from, member.access_until
    )
    audit.record(
        db,
        actor.id,
        "member.update",
        "facility_member",
        member.id,
        {"role": member.role.value},
    )
    db.commit()
    return member


def remove_member(
    db: Session, facility: Facility, actor: User, member_id: uuid.UUID
) -> None:
    """Вилучає учасника з об'єкта (крім власника)."""
    member = _get_editable_member(db, facility, member_id)
    db.delete(member)
    audit.record(db, actor.id, "member.remove", "facility_member", member.id)
    db.commit()


def _get_editable_member(
    db: Session, facility: Facility, member_id: uuid.UUID
) -> FacilityMember:
    member = get_in_facility(db, FacilityMember, member_id, facility.id)
    if member.role == FacilityRole.OWNER:
        raise ForbiddenError("owner_immutable")
    return member


def _check_access_period(
    db: Session,
    facility: Facility,
    role: FacilityRole,
    access_from: datetime | None,
    access_until: datetime | None,
) -> None:
    """Гість має обмежений строк доступу, і лише якщо дозволяє тариф власника."""
    if access_from and access_until and access_from >= access_until:
        raise BadRequestError("invalid_period")
    if role != FacilityRole.GUEST:
        return
    if access_until is None:
        raise BadRequestError("guest_period_required")
    owner = db.get(User, facility.owner_id)
    if owner is None or not owner.tariff_plan.guest_access:
        raise ForbiddenError("tariff_feature")
