"""Стисла хронологія інциденту (ФМ-7, СЧ-7).

Постачальник хронології отримує лише структуровані події тривоги (номер,
тип, зона, час), без імен користувачів (мінімізація даних). Результат має
дві частини: «Факти за даними датчиків» (кожне твердження з номером події)
і «Припущення». Постачальник не має жодних засобів керування охороною:
він лише повертає текст.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ForbiddenError, NotFoundError
from app.i18n import translate
from app.models.devices import Sensor
from app.models.enums import EventType, Locale
from app.models.events import Alarm, AlarmEvent, Event, IncidentSummary
from app.models.facilities import Facility, Zone
from app.models.users import User
from app.services.access import Permission, require_access


@dataclass(frozen=True)
class IncidentEvent:
    """Подія інциденту без персональних даних."""

    number: int
    event_type: EventType
    zone: str
    occurred_at: datetime


@dataclass(frozen=True)
class Summary:
    """Факти й припущення, підготовлені постачальником."""

    facts: str
    assumptions: str


class SummaryProvider(Protocol):
    """Постачальник хронології (шаблонний або зовнішня мовна модель)."""

    name: str

    def summarize(self, events: Sequence[IncidentEvent], locale: Locale) -> Summary:
        """Формує факти й припущення за подіями інциденту."""


class TemplateSummaryProvider:
    """Детермінований шаблонний генератор (за замовчуванням, без мережі)."""

    name = "template-v1"

    def summarize(self, events: Sequence[IncidentEvent], locale: Locale) -> Summary:
        """Факти — перелік подій; припущення — за простими правилами."""
        facts = [
            translate("incident.fact", locale).format(
                number=event.number,
                time=event.occurred_at.strftime("%H:%M:%S"),
                zone=event.zone,
                event=translate(f"event.{event.event_type.value}", locale),
            )
            for event in events
        ]
        return Summary("\n".join(facts), translate(_assumption_key(events), locale))


class ExternalSummaryProvider:
    """Заглушка зовнішньої мовної моделі: налаштовується змінними середовища.

    Реальних викликів у ЛБ3 немає; ключі доступу в репозиторій не потрапляють.
    """

    name = "external-llm"

    def __init__(self, api_url: str | None, model: str | None) -> None:
        self.api_url = api_url
        self.model = model

    def summarize(self, events: Sequence[IncidentEvent], locale: Locale) -> Summary:
        """Завжди повідомляє, що зовнішній сервіс недоступний."""
        raise AppError(503, "llm_unavailable")


def default_provider() -> SummaryProvider:
    """Постачальник за налаштуванням SUMMARY_PROVIDER."""
    if settings.summary_provider == "external":
        return ExternalSummaryProvider(settings.llm_api_url, settings.llm_model)
    return TemplateSummaryProvider()


def summarize_alarm(
    db: Session,
    user: User,
    alarm_id: uuid.UUID,
    locale: Locale,
    provider: SummaryProvider,
) -> IncidentSummary:
    """Формує й зберігає хронологію тривоги (тариф із функцією хронології)."""
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError()
    facility, _ = require_access(db, alarm.facility_id, user, Permission.VIEW_EVENTS)
    _require_tariff(db, facility)
    summary = provider.summarize(_incident_events(db, alarm), locale)
    record = IncidentSummary(
        alarm_id=alarm.id,
        language=locale.value,
        facts=summary.facts,
        assumptions=summary.assumptions,
        model_name=provider.name,
        created_by=user.id,
    )
    db.add(record)
    db.commit()
    return record


def list_summaries(
    db: Session, user: User, alarm_id: uuid.UUID
) -> list[IncidentSummary]:
    """Раніше сформовані хронології тривоги."""
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise NotFoundError()
    require_access(db, alarm.facility_id, user, Permission.VIEW_EVENTS)
    stmt = (
        select(IncidentSummary)
        .where(IncidentSummary.alarm_id == alarm.id)
        .order_by(IncidentSummary.created_at.desc())
    )
    return list(db.scalars(stmt))


def _incident_events(db: Session, alarm: Alarm) -> list[IncidentEvent]:
    rows = db.execute(
        select(Event, Zone.name)
        .join(AlarmEvent, AlarmEvent.event_id == Event.id)
        .outerjoin(Sensor, Sensor.id == Event.sensor_id)
        .outerjoin(Zone, Zone.id == Sensor.zone_id)
        .where(AlarmEvent.alarm_id == alarm.id)
        .order_by(Event.occurred_at, Event.id)
    ).all()
    return [
        IncidentEvent(event.id, event.event_type, zone or "—", event.occurred_at)
        for event, zone in rows
    ]


def _assumption_key(events: Sequence[IncidentEvent]) -> str:
    """Найімовірніше пояснення за типами подій інциденту."""
    types = {event.event_type for event in events}
    if EventType.TAMPER in types:
        return "incident.assume_tamper"
    if EventType.OPENED in types and EventType.MOTION in types:
        return "incident.assume_intrusion"
    if EventType.OPENED in types:
        return "incident.assume_door_only"
    return "incident.assume_motion_only"


def _require_tariff(db: Session, facility: Facility) -> None:
    owner = db.get_one(User, facility.owner_id)
    if not owner.tariff_plan.incident_timeline:
        raise ForbiddenError("tariff_feature")
