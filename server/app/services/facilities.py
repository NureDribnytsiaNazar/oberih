"""Об'єкти охорони та їхні налаштування."""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ForbiddenError
from app.models.devices import Node
from app.models.enums import FacilityRole
from app.models.facilities import Facility, FacilityMember, FacilitySettings
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.facilities import (
    FacilityCreate,
    FacilitySettingsUpdate,
    FacilityUpdate,
)
from app.services import audit
from app.services.common import apply_changes
from app.services.users import validate_timezone


def list_for_user(
    db: Session, user: User, params: PageParams
) -> tuple[list[Facility], int]:
    """Об'єкти, учасником яких є користувач (власні та спільні)."""
    stmt = (
        select(Facility)
        .join(FacilityMember, FacilityMember.facility_id == Facility.id)
        .where(FacilityMember.user_id == user.id)
        .order_by(Facility.created_at, Facility.id)
    )
    return paginate(db, stmt, params)


def create(db: Session, user: User, data: FacilityCreate) -> Facility:
    """Створює об'єкт з налаштуваннями за замовчуванням; автор стає власником.

    Кількість власних об'єктів обмежується тарифним планом (ВО-8).
    """
    owned = db.scalar(
        select(func.count()).select_from(Facility).where(Facility.owner_id == user.id)
    )
    if (owned or 0) >= user.tariff_plan.max_facilities:
        raise ForbiddenError("tariff_limit")
    validate_timezone(data.timezone)

    facility = Facility(owner_id=user.id, **data.model_dump())
    # Значення параметрів за замовчуванням задано в моделі FacilitySettings.
    facility.settings = FacilitySettings()
    facility.members.append(FacilityMember(user_id=user.id, role=FacilityRole.OWNER))
    db.add(facility)
    db.flush()
    audit.record(db, user.id, "facility.create", "facility", facility.id)
    db.commit()
    return facility


def update(db: Session, facility: Facility, data: FacilityUpdate) -> Facility:
    """Змінює назву, адресу або часовий пояс об'єкта."""
    if data.timezone is not None:
        validate_timezone(data.timezone)
    apply_changes(facility, data)
    db.commit()
    return facility


def remove(db: Session, user: User, facility: Facility) -> None:
    """Видаляє об'єкт разом з усіма даними (право на видалення, GDPR).

    Спочатку видаляються вузли (а з ними датчики), бо датчики посилаються
    на зони з обмеженням RESTRICT; решту видаляє каскад у БД.
    """
    facility_id = facility.id
    db.execute(delete(Node).where(Node.facility_id == facility_id))
    db.execute(delete(Facility).where(Facility.id == facility_id))
    audit.record(db, user.id, "facility.delete", "facility", facility_id)
    db.commit()


def update_settings(
    db: Session, facility: Facility, data: FacilitySettingsUpdate
) -> FacilitySettings:
    """Змінює параметри бізнес-логіки об'єкта."""
    settings = facility.settings
    apply_changes(settings, data)
    if settings.alarm_threshold > settings.confirmed_threshold:
        db.rollback()
        raise BadRequestError("invalid_thresholds")
    db.commit()
    return settings
