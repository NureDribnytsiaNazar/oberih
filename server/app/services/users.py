"""Профіль користувача, експорт і знеособлення персональних даних (GDPR)."""

import uuid
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, UnauthorizedError
from app.models.events import AlarmAcknowledgement, ArmingLogEntry
from app.models.facilities import Facility, FacilityMember, NotificationSetting
from app.models.users import PushToken, RefreshToken, User
from app.schemas.users import UserExport, UserUpdate
from app.security import verify_password
from app.services import audit

ANONYMIZED_NAME = "—"


def validate_timezone(name: str) -> str:
    """Перевіряє назву часового поясу IANA (наприклад, Europe/Kyiv)."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise BadRequestError("invalid_timezone")
    return name


def update_profile(db: Session, user: User, data: UserUpdate) -> User:
    """Змінює лише передані поля профілю."""
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "timezone" in changes:
        validate_timezone(changes["timezone"])
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return user


def export_data(db: Session, user: User) -> UserExport:
    """Збирає всі персональні дані користувача в одному документі."""
    memberships = db.execute(
        select(FacilityMember, Facility.name)
        .join(Facility, Facility.id == FacilityMember.facility_id)
        .where(FacilityMember.user_id == user.id)
    ).all()
    arming = db.scalars(
        select(ArmingLogEntry)
        .where(ArmingLogEntry.user_id == user.id)
        .order_by(ArmingLogEntry.created_at)
    ).all()
    acks = db.scalars(
        select(AlarmAcknowledgement)
        .where(AlarmAcknowledgement.user_id == user.id)
        .order_by(AlarmAcknowledgement.created_at)
    ).all()
    audit.record(db, user.id, "user.export", "user", user.id)
    db.commit()
    return UserExport(
        exported_at=datetime.now(UTC),
        profile={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "locale": user.locale.value,
            "timezone": user.timezone,
            "measurement_system": user.measurement_system.value,
            "totp_enabled": user.totp_enabled,
            "tariff_plan": user.tariff_plan.code,
            "privacy_consent_at": _iso(user.privacy_consent_at),
            "created_at": _iso(user.created_at),
        },
        memberships=[
            {
                "facility_id": str(member.facility_id),
                "facility_name": name,
                "role": member.role.value,
                "access_from": _iso(member.access_from),
                "access_until": _iso(member.access_until),
            }
            for member, name in memberships
        ],
        arming_actions=[
            {
                "facility_id": str(entry.facility_id),
                "from_mode": entry.from_mode.value,
                "to_mode": entry.to_mode.value,
                "source": entry.source.value,
                "ip_address": entry.ip_address,
                "created_at": _iso(entry.created_at),
            }
            for entry in arming
        ],
        alarm_acknowledgements=[
            {
                "alarm_id": str(ack.alarm_id),
                "action": ack.action.value,
                "comment": ack.comment,
                "created_at": _iso(ack.created_at),
            }
            for ack in acks
        ],
    )


def anonymize(db: Session, user: User, password: str) -> None:
    """Знеособлює обліковий запис замість видалення.

    Записи журналів залишаються (вони лише для додавання), але більше не
    пов'язані з персональними даними: пошта й ім'я замінюються, вхід
    стає неможливим, сесії та членства видаляються.
    """
    if not verify_password(password, user.password_hash):
        raise UnauthorizedError("reauth_failed")
    owns = db.scalar(select(Facility.id).where(Facility.owner_id == user.id).limit(1))
    if owns is not None:
        raise ConflictError("owns_facilities")

    user_id: uuid.UUID = user.id
    for model in (RefreshToken, PushToken, NotificationSetting, FacilityMember):
        db.execute(delete(model).where(model.user_id == user_id))
    user.email = f"deleted-{user_id}@anonymized.invalid"
    user.full_name = ANONYMIZED_NAME
    # Рядок не є хешем Argon2, тому жоден пароль із ним не збігається.
    user.password_hash = "!"
    user.totp_secret = None
    user.totp_enabled = False
    user.is_active = False
    user.anonymized_at = datetime.now(UTC)
    audit.record(db, user_id, "user.anonymize", "user", user_id)
    db.commit()


def _iso(value: datetime | None) -> Any:
    return value.isoformat() if value else None
