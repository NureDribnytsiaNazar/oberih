"""Регіональні формати (ФМ-10): місцевий час, дати, сортування, мови.

Час у БД і в полях API зберігається в UTC; тут він перетворюється на
місцевий час користувача з урахуванням переходу на літній час і
форматується за правилами його мови та обраного формату часу.
"""

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from babel.dates import format_datetime
from sqlalchemy import ColumnElement
from sqlalchemy.orm import QueryableAttribute

from app.models.enums import Locale, TimeFormat

BABEL_LOCALES = {Locale.UK: "uk_UA", Locale.EN: "en_US"}
# ICU-правила сортування PostgreSQL для кожної мови інтерфейсу.
COLLATIONS = {Locale.UK: "uk-UA-x-icu", Locale.EN: "en-US-x-icu"}
DATE_PATTERNS = {Locale.UK: "dd.MM.yyyy", Locale.EN: "MM/dd/yyyy"}
TIME_PATTERNS = {TimeFormat.H24: "HH:mm:ss", TimeFormat.H12: "h:mm:ss a"}


@dataclass(frozen=True)
class LocaleInfo:
    """Опис мови для клієнтів: назва, напрям тексту, чи підтримується."""

    code: str
    name: str
    direction: str
    supported: bool


# Підтримувані мови та приклади мов із письмом справа наліво: сервер лише
# повідомляє напрям тексту, застосовує його клієнт.
LOCALES = (
    LocaleInfo("uk", "Українська", "ltr", True),
    LocaleInfo("en", "English", "ltr", True),
    LocaleInfo("ar", "العربية", "rtl", False),
    LocaleInfo("he", "עברית", "rtl", False),
)


def to_local(moment: datetime, tz_name: str) -> datetime:
    """UTC -> місцевий час часового поясу (літній час враховується)."""
    return moment.astimezone(ZoneInfo(tz_name))


def format_local(
    moment: datetime, tz_name: str, locale: Locale, time_format: TimeFormat
) -> str:
    """Місцеві дата й час за правилами мови та формату часу користувача."""
    pattern = f"{DATE_PATTERNS[locale]} {TIME_PATTERNS[time_format]}"
    return format_datetime(
        moment,
        format=pattern,
        tzinfo=ZoneInfo(tz_name),
        locale=BABEL_LOCALES[locale],
    )


def collated(column: QueryableAttribute[str], locale: Locale) -> ColumnElement[str]:
    """Стовпець із правилами сортування мови (Є, Ж, І — в українському порядку)."""
    return column.collate(COLLATIONS[locale])
