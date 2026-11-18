"""Керування користувачами адміністратором платформи (ФМ-9, СЧ-9).

Кожна дія записується в журнал аудиту. Знеособлені користувачі не
редагуються; останнього адміністратора не можна позбавити прав.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, NotFoundError
from app.models.users import RefreshToken, TariffPlan, User
from app.services import audit


def get_user(db: Session, admin: User, user_id: uuid.UUID) -> User:
    """Обліковий запис за ідентифікатором (перегляд фіксується в аудиті)."""
    user = _get(db, user_id)
    audit.record(db, admin.id, "admin.user_view", "user", user.id)
    db.commit()
    return user


def block(db: Session, admin: User, user_id: uuid.UUID) -> User:
    """Блокує вхід і завершує всі сесії користувача."""
    user = _get_editable(db, user_id)
    if user.id == admin.id:
        raise ConflictError("cannot_block_self")
    user.blocked_at = datetime.now(UTC)
    _revoke_sessions(db, user)
    audit.record(db, admin.id, "admin.user_block", "user", user.id)
    db.commit()
    return user


def unblock(db: Session, admin: User, user_id: uuid.UUID) -> User:
    """Знімає блокування."""
    user = _get_editable(db, user_id)
    user.blocked_at = None
    audit.record(db, admin.id, "admin.user_unblock", "user", user.id)
    db.commit()
    return user


def set_platform_admin(
    db: Session, admin: User, user_id: uuid.UUID, value: bool
) -> User:
    """Надає або знімає права адміністратора платформи."""
    user = _get_editable(db, user_id)
    if not value and user.is_platform_admin and _admin_count(db) <= 1:
        raise ConflictError("last_admin")
    user.is_platform_admin = value
    audit.record(
        db,
        admin.id,
        "admin.user_platform_admin",
        "user",
        user.id,
        {"is_platform_admin": value},
    )
    db.commit()
    return user


def revoke_sessions(db: Session, admin: User, user_id: uuid.UUID) -> int:
    """Примусово завершує всі сесії (відкликає токени оновлення)."""
    user = _get(db, user_id)
    count = _revoke_sessions(db, user)
    audit.record(
        db, admin.id, "admin.user_sessions_revoke", "user", user.id, {"count": count}
    )
    db.commit()
    return count


def reset_totp(db: Session, admin: User, user_id: uuid.UUID) -> User:
    """Вимикає двофакторну автентифікацію (втрачено автентифікатор)."""
    user = _get_editable(db, user_id)
    user.totp_secret = None
    user.totp_enabled = False
    audit.record(db, admin.id, "admin.user_totp_reset", "user", user.id)
    db.commit()
    return user


def set_tariff(db: Session, admin: User, user_id: uuid.UUID, code: str) -> User:
    """Змінює тарифний план користувача."""
    user = _get_editable(db, user_id)
    tariff = db.scalar(select(TariffPlan).where(TariffPlan.code == code))
    if tariff is None:
        raise BadRequestError("unknown_tariff")
    user.tariff_plan = tariff
    audit.record(db, admin.id, "admin.user_tariff", "user", user.id, {"tariff": code})
    db.commit()
    return user


def _get(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError()
    return user


def _get_editable(db: Session, user_id: uuid.UUID) -> User:
    user = _get(db, user_id)
    if user.anonymized_at is not None:
        raise ConflictError("user_anonymized")
    return user


def _admin_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_platform_admin, User.anonymized_at.is_(None))
        )
        or 0
    )


def _revoke_sessions(db: Session, user: User) -> int:
    result = db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    return int(getattr(result, "rowcount", 0) or 0)
