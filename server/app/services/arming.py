"""Автомат режимів охорони (рисунок 2 Vision & Scope).

Переходи, які ініціює користувач:
    disarmed --(away)--> exit_delay --(час минув)--> armed_away
    disarmed --(home)--> armed_home
    exit_delay, armed_away, armed_home, entry_delay, alarm --(зняття)--> disarmed

Переходи за подіями датчиків (entry_delay, alarm) реалізуються в ЛБ3;
у ЛБ2 є лише заглушка для події втручання в корпус (див. device.py).
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ConflictError, ForbiddenError
from app.models.enums import ActionSource, AuthMethod, FacilityMode
from app.models.events import ArmingLogEntry
from app.models.facilities import Facility, FacilityMember
from app.models.users import User
from app.pagination import PageParams, paginate
from app.schemas.events import ArmMode, DisarmRequest
from app.services.access import Permission, has_permission
from app.services.reauth import confirm_action

DISARMABLE_MODES = {
    FacilityMode.EXIT_DELAY,
    FacilityMode.ARMED_AWAY,
    FacilityMode.ARMED_HOME,
    FacilityMode.ENTRY_DELAY,
    FacilityMode.ALARM,
}


def arm_target(current: FacilityMode, mode: ArmMode, exit_delay_s: int) -> FacilityMode:
    """Режим, у який переходить об'єкт після команди постановки."""
    if current != FacilityMode.DISARMED:
        raise ConflictError("invalid_transition")
    if mode == ArmMode.HOME:
        # Режим «Вдома» вмикається без затримки виходу.
        return FacilityMode.ARMED_HOME
    if exit_delay_s > 0:
        return FacilityMode.EXIT_DELAY
    return FacilityMode.ARMED_AWAY


def change_mode(
    db: Session,
    facility: Facility,
    to_mode: FacilityMode,
    source: ActionSource,
    user_id: uuid.UUID | None = None,
    auth_method: AuthMethod | None = None,
    ip_address: str | None = None,
) -> None:
    """Змінює режим об'єкта і додає запис до журналу охорони (ПК-3)."""
    db.add(
        ArmingLogEntry(
            facility_id=facility.id,
            user_id=user_id,
            from_mode=facility.mode,
            to_mode=to_mode,
            source=source,
            auth_method=auth_method,
            ip_address=ip_address,
        )
    )
    facility.mode = to_mode
    facility.mode_changed_at = datetime.now(UTC)


def finish_exit_delay(db: Session, facility: Facility) -> None:
    """Якщо затримка виходу минула, переводить об'єкт під охорону.

    Окремого планувальника в ЛБ2 немає, тому перевірка виконується під час
    кожного звернення до об'єкта через API.
    """
    if facility.mode != FacilityMode.EXIT_DELAY:
        return
    ends_at = facility.mode_changed_at + timedelta(
        seconds=facility.settings.exit_delay_s
    )
    if datetime.now(UTC) >= ends_at:
        change_mode(db, facility, FacilityMode.ARMED_AWAY, ActionSource.SYSTEM)
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
    finish_exit_delay(db, facility)
    target = arm_target(facility.mode, mode, facility.settings.exit_delay_s)
    change_mode(db, facility, target, source, user.id, None, ip_address)
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
    """
    finish_exit_delay(db, facility)
    if facility.mode not in DISARMABLE_MODES:
        raise ConflictError("invalid_transition")
    if facility.mode == FacilityMode.ALARM and not has_permission(
        member, Permission.ACK_ALARM
    ):
        raise ForbiddenError()
    method = confirm_action(user, data.confirmation)
    change_mode(
        db, facility, FacilityMode.DISARMED, data.source, user.id, method, ip_address
    )
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
