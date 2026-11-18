"""Подання подій і тривог для конкретного користувача (ФМ-10).

Значення в UTC залишаються без змін, а поруч додаються місцевий час
(часовий пояс користувача або параметр tz), його текст за мовою й
форматом часу та фізичні величини в обраній системі одиниць.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.l10n import format_local, to_local
from app.models.enums import Locale, MeasurementSystem, TimeFormat
from app.models.events import Alarm, Event
from app.models.users import User
from app.schemas.events import AlarmOut, EventOut, Measurement
from app.services.users import validate_timezone
from app.units import Quantity, length, temperature

# Ключ у payload події (метричні одиниці) -> назва величини й перетворення.
MEASUREMENTS: dict[
    str, tuple[str, Callable[[Decimal, MeasurementSystem], Quantity]]
] = {
    "temperature_c": ("temperature", temperature),
    "distance_m": ("distance", length),
}


@dataclass(frozen=True)
class ViewerPrefs:
    """Регіональні налаштування того, хто переглядає дані."""

    tz: str
    locale: Locale
    time_format: TimeFormat
    system: MeasurementSystem


def viewer_prefs(user: User, locale: Locale, tz: str | None = None) -> ViewerPrefs:
    """Налаштування з профілю; tz із запиту має пріоритет над профілем."""
    return ViewerPrefs(
        tz=validate_timezone(tz) if tz else user.timezone,
        locale=locale,
        time_format=user.time_format,
        system=user.measurement_system,
    )


def event_view(event: Event, prefs: ViewerPrefs) -> EventOut:
    """Подія з місцевим часом і величинами в одиницях користувача."""
    view = EventOut.model_validate(event)
    view.time_local = to_local(event.occurred_at, prefs.tz)
    view.time_local_text = format_local(
        event.occurred_at, prefs.tz, prefs.locale, prefs.time_format
    )
    view.measurements = _measurements(event.payload, prefs.system)
    return view


def alarm_view(alarm: Alarm, prefs: ViewerPrefs) -> AlarmOut:
    """Тривога з місцевим часом відкриття."""
    view = AlarmOut.model_validate(alarm)
    view.opened_at_local = to_local(alarm.opened_at, prefs.tz)
    view.opened_at_text = format_local(
        alarm.opened_at, prefs.tz, prefs.locale, prefs.time_format
    )
    return view


def _measurements(
    payload: dict[str, Any] | None, system: MeasurementSystem
) -> list[Measurement]:
    """Відомі фізичні величини з payload (некоректні значення пропускаються)."""
    result = []
    for key, (name, convert) in MEASUREMENTS.items():
        raw = (payload or {}).get(key)
        if raw is None:
            continue
        try:
            quantity = convert(Decimal(str(raw)), system)
        except InvalidOperation:
            continue
        result.append(Measurement(name=name, value=quantity.value, unit=quantity.unit))
    return result
