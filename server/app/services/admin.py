"""Адміністрування платформи: користувачі, журнал аудиту, тарифи."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.admin import AuditLogEntry
from app.models.devices import Node
from app.models.events import Alarm, Event
from app.models.facilities import Facility
from app.models.users import TariffPlan, User
from app.pagination import PageParams, paginate
from app.services import audit


def list_users(db: Session, admin: User, params: PageParams) -> tuple[list[User], int]:
    """Усі користувачі; перегляд фіксується в журналі доступу до даних."""
    stmt = (
        select(User)
        .options(joinedload(User.tariff_plan))
        .order_by(User.created_at, User.id)
    )
    page = paginate(db, stmt, params)
    audit.record(db, admin.id, "admin.users_view")
    db.commit()
    return page


def list_audit_log(
    db: Session,
    params: PageParams,
    user_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> tuple[list[AuditLogEntry], int]:
    """Журнал аудиту з фільтрами; новіші записи першими."""
    stmt = select(AuditLogEntry)
    if user_id is not None:
        stmt = stmt.where(AuditLogEntry.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLogEntry.action == action)
    if entity_type is not None:
        stmt = stmt.where(AuditLogEntry.entity_type == entity_type)
    stmt = stmt.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
    return paginate(db, stmt, params)


def list_tariffs(db: Session) -> list[TariffPlan]:
    """Тарифні плани за зростанням ціни."""
    return list(db.scalars(select(TariffPlan).order_by(TariffPlan.price_month)))


def system_stats(db: Session, admin: User) -> dict[str, int]:
    """Кількість основних записів і розмір архіву подій у байтах."""
    counts = {
        name: int(db.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in (
            ("users", User),
            ("facilities", Facility),
            ("nodes", Node),
            ("events", Event),
            ("alarms", Alarm),
        )
    }
    archive = sum(
        int(db.scalar(select(func.pg_total_relation_size(table))) or 0)
        for table in ("events", "alarms", "alarm_events")
    )
    counts["archive_bytes"] = archive
    counts["database_bytes"] = int(
        db.scalar(select(func.pg_database_size(func.current_database()))) or 0
    )
    audit.record(db, admin.id, "admin.stats_view")
    db.commit()
    return counts
