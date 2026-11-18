"""Керування режимом охорони об'єкта.

Усі зміни режиму виконуються через transition(): вона перевіряє перехід
за автоматом (state_machine.py), змінює режим і додає запис до журналу
охорони. Команди користувача (arm, disarm), конвеєр подій і фоновий
виконавець таймерів користуються лише нею.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ForbiddenError
from app.models.enums import ActionSource, AuthMethod, FacilityMode
from app.models.events import ArmingLogEntry
from app.models.facilities import Facility, FacilityMember
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.events import ArmMode, DisarmRequest
from app.services.access import Permission, has_permission
from app.services.alarm_store import close_open_alarms
from app.services.reauth import confirm_action
from app.services.state_machine import ModeTrigger, expired_delay_trigger, next_mode

ARM_TRIGGERS = {ArmMode.AWAY: ModeTrigger.ARM_AWAY, ArmMode.HOME: ModeTrigger.ARM_HOME}


def transition(
    db: Session,
    facility: Facility,
    trigger: ModeTrigger,
    source: ActionSource,
    user_id: uuid.UUID | None = None,
    auth_method: AuthMethod | None = None,
    ip_address: str | None = None,
    now: datetime | None = None,
) -> FacilityMode:
    """Єдина точка зміни режиму. Повертає новий режим.

    Недопустимий перехід піднімає ConflictError. Повторна миттєва тривога
    в режимі alarm нічого не змінює й не пише в журнал.
    """
    target = next_mode(facility.mode, trigger, _delay_for(facility, trigger))
    if target == facility.mode:
        return target
    db.add(
        ArmingLogEntry(
            facility_id=facility.id,
            user_id=user_id,
            from_mode=facility.mode,
            to_mode=target,
            source=source,
            auth_method=auth_method,
            ip_address=ip_address,
        )
    )
    facility.mode = target
    facility.mode_changed_at = now or datetime.now(UTC)
    return target


def apply_due_timer(
    db: Session, facility: Facility, now: datetime | None = None
) -> ModeTrigger | None:
    """Завершує затримку виходу чи входу, якщо її час минув.

    Викликається фоновим виконавцем (timers.process_timers) і, як запасний
    механізм, під час звернення до об'єкта через API. Сам не фіксує
    транзакцію — це робить той, хто викликає.
    """
    now = now or datetime.now(UTC)
    settings = facility.settings
    trigger = expired_delay_trigger(
        facility.mode,
        facility.mode_changed_at,
        settings.exit_delay_s,
        settings.entry_delay_s,
        now,
    )
    if trigger is not None:
        transition(db, facility, trigger, ActionSource.SYSTEM, now=now)
    return trigger


def refresh_mode(db: Session, facility: Facility) -> None:
    """Запасний лінивий механізм: застосовує прострочений таймер і фіксує."""
    if apply_due_timer(db, facility) is not None:
        db.commit()


def arm(
    db: Session,
    facility: Facility,
    user: User,
    mode: ArmMode,
    source: ActionSource,
    ip_address: str | None,
) -> Facility:
    """Постановка на охорону в повному режимі або в режимі «Вдома»."""
    apply_due_timer(db, facility)
    transition(db, facility, ARM_TRIGGERS[mode], source, user.id, None, ip_address)
    db.commit()
    return facility


def disarm(
    db: Session,
    facility: Facility,
    member: FacilityMember,
    user: User,
    data: DisarmRequest,
    ip_address: str | None,
) -> Facility:
    """Зняття з охорони з повторним підтвердженням паролем або кодом TOTP.

    Скидати тривогу може лише той, кому дозволено підтверджувати тривоги.
    Зняття під час затримки входу скасовує відкриту тривогу (законний вхід).
    """
    apply_due_timer(db, facility)
    if facility.mode == FacilityMode.ALARM and not has_permission(
        member, Permission.ACK_ALARM
    ):
        raise ForbiddenError()
    next_mode(facility.mode, ModeTrigger.DISARM)  # перевірка до запиту пароля
    method = confirm_action(user, data.confirmation)
    was_entry_delay = facility.mode == FacilityMode.ENTRY_DELAY
    transition(
        db,
        facility,
        ModeTrigger.DISARM,
        data.source,
        user.id,
        method,
        ip_address,
    )
    if was_entry_delay:
        close_open_alarms(db, facility.id, cancelled=True)
    db.commit()
    return facility


def list_log(
    db: Session, facility: Facility, params: PageParams
) -> tuple[list[ArmingLogEntry], int]:
    """Журнал постановки та зняття, найновіші записи першими."""
    stmt = (
        select(ArmingLogEntry)
        .where(ArmingLogEntry.facility_id == facility.id)
        .order_by(ArmingLogEntry.created_at.desc(), ArmingLogEntry.id.desc())
    )
    return paginate(db, stmt, params)


def _delay_for(facility: Facility, trigger: ModeTrigger) -> int:
    """Тривалість затримки, у яку веде тригер (для нульових затримок)."""
    if trigger == ModeTrigger.ARM_AWAY:
        return facility.settings.exit_delay_s
    if trigger == ModeTrigger.INTRUSION:
        return facility.settings.entry_delay_s
    return 0
