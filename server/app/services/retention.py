"""Політика зберігання даних: видалення застарілих подій і тривог (GDPR).

Строк зберігання визначає тариф власника об'єкта (tariff_plans.archive_days).
Видалення виконується пакетами, щоб не блокувати таблиці надовго.
Журнали, захищені тригерами (arming_log, audit_log), не видаляються.
"""

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, delete, func, literal, select
from sqlalchemy.orm import Session

from app.models.enums import AlarmStatus
from app.models.events import Alarm, Event
from app.models.facilities import Facility
from app.models.users import TariffPlan, User
from app.services import audit

BATCH_SIZE = 1000
CLOSED_ALARM_STATUSES = (AlarmStatus.RESOLVED, AlarmStatus.CANCELLED)


@dataclass
class PurgeReport:
    """Скільки записів видалено."""

    alarms: int = 0
    events: int = 0


def purge_expired_data(
    db: Session, now: datetime, actor_id: Any = None, batch_size: int = BATCH_SIZE
) -> PurgeReport:
    """Видаляє закриті тривоги й події, старші за строк зберігання тарифу.

    Спочатку тривоги (разом із ними каскадно видаляються зв'язки з подіями
    та підтвердження), потім події. Підсумок записується в журнал аудиту.
    """
    report = PurgeReport()
    expired_alarms = _with_tariff(select(Alarm.id), Alarm.facility_id).where(
        Alarm.opened_at < _cutoff(now),
        Alarm.status.in_(CLOSED_ALARM_STATUSES),
    )
    report.alarms = _delete_in_batches(db, Alarm, expired_alarms, batch_size)
    expired_events = _with_tariff(select(Event.id), Event.facility_id).where(
        Event.occurred_at < _cutoff(now)
    )
    report.events = _delete_in_batches(db, Event, expired_events, batch_size)
    audit.record(db, actor_id, "data.purge", details=asdict(report))
    db.commit()
    return report


def _with_tariff(stmt: Select[Any], facility_column: Any) -> Select[Any]:
    """Додає до запиту тариф власника об'єкта."""
    return (
        stmt.join(Facility, Facility.id == facility_column)
        .join(User, User.id == Facility.owner_id)
        .join(TariffPlan, TariffPlan.id == User.tariff_plan_id)
    )


def _cutoff(now: datetime) -> ColumnElement[Any]:
    """Межа зберігання: now − archive_days тарифу (обчислюється в SQL)."""
    return literal(now) - func.make_interval(0, 0, 0, TariffPlan.archive_days)


def _delete_in_batches(
    db: Session, model: Any, ids_stmt: Select[Any], batch_size: int
) -> int:
    """Видаляє записи за підзапитом ідентифікаторів пакетами по batch_size."""
    total = 0
    while True:
        batch = ids_stmt.limit(batch_size).scalar_subquery()
        result = db.execute(
            delete(model).where(model.id.in_(batch)),
            execution_options={"synchronize_session": False},
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)
        total += deleted
        if deleted < batch_size:
            return total
