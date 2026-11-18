"""Експорт архіву подій у CSV (ФМ-6, ФМ-10).

Файл у кодуванні UTF-8 з позначкою BOM (щоб табличні редактори коректно
показували кирилицю). Роздільник, назви стовпців і формат місцевого часу
залежать від локалі: для uk — «;» і дати на кшталт 25.10.2026, 01:30:00,
для en — «,» і Oct 25, 2026, 1:30:00 AM.
"""

import csv
import io
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

from babel.dates import format_datetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.i18n import translate
from app.models.devices import Sensor
from app.models.enums import Locale
from app.models.events import Event
from app.models.facilities import Facility, Zone

DELIMITERS = {Locale.UK: ";", Locale.EN: ","}
BABEL_LOCALES = {Locale.UK: "uk_UA", Locale.EN: "en_US"}
COLUMNS = (
    "csv.id",
    "csv.time_utc",
    "csv.time_local",
    "csv.event",
    "csv.zone",
    "csv.sensor",
    "csv.seq",
)
BATCH_SIZE = 500


def format_local(moment: datetime, tz: ZoneInfo, locale: Locale) -> str:
    """Місцевий час у форматі локалі (з урахуванням літнього часу)."""
    return format_datetime(
        moment, format="medium", tzinfo=tz, locale=BABEL_LOCALES[locale]
    )


def events_csv(
    db: Session,
    facility: Facility,
    locale: Locale,
    tz_name: str,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
) -> Iterator[str]:
    """Рядки CSV по черзі, щоб не тримати весь архів у пам'яті."""
    tz = ZoneInfo(tz_name)
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=DELIMITERS[locale], lineterminator="\r\n")
    writer.writerow([translate(column, locale) for column in COLUMNS])
    yield "﻿" + _drain(buffer)

    stmt = (
        select(Event, Sensor.name, Zone.name)
        .outerjoin(Sensor, Sensor.id == Event.sensor_id)
        .outerjoin(Zone, Zone.id == Sensor.zone_id)
        .where(Event.facility_id == facility.id)
        .order_by(Event.occurred_at, Event.id)
        .execution_options(yield_per=BATCH_SIZE)
    )
    if occurred_from is not None:
        stmt = stmt.where(Event.occurred_at >= occurred_from)
    if occurred_to is not None:
        stmt = stmt.where(Event.occurred_at < occurred_to)
    for event, sensor_name, zone_name in db.execute(stmt):
        writer.writerow(
            [
                event.id,
                event.occurred_at.isoformat(),
                format_local(event.occurred_at, tz, locale),
                translate(f"event.{event.event_type.value}", locale),
                zone_name or "",
                sensor_name or "",
                "" if event.seq is None else event.seq,
            ]
        )
        yield _drain(buffer)


def _drain(buffer: io.StringIO) -> str:
    """Забирає накопичений текст із буфера й очищає його."""
    text = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate()
    return text
