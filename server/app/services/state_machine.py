"""Скінченний автомат режимів охорони (рисунок 2 Vision & Scope).

Чистий модуль без роботи з БД: за поточним режимом і подією-тригером
повертає новий режим або піднімає помилку недопустимого переходу. Його
використовують API, конвеєр подій, фоновий виконавець і відтворення
тестових сценаріїв, тому правила переходів описано лише тут.
"""

import enum
from datetime import datetime, timedelta

from app.errors import ConflictError
from app.models.enums import FacilityMode


class ModeTrigger(str, enum.Enum):
    """Подія, що може змінити режим об'єкта."""

    ARM_AWAY = "arm_away"  # команда повної постановки
    ARM_HOME = "arm_home"  # команда режиму «Вдома»
    EXIT_DELAY_EXPIRED = "exit_delay_expired"  # минула затримка виходу
    INTRUSION = "intrusion"  # спрацювання датчика під охороною
    INSTANT_ALARM = "instant_alarm"  # тампер або цілодобова зона
    ENTRY_DELAY_EXPIRED = "entry_delay_expired"  # минула затримка входу
    DISARM = "disarm"  # зняття з охорони уповноваженим користувачем


ARMED_MODES = frozenset({FacilityMode.ARMED_AWAY, FacilityMode.ARMED_HOME})
DISARMABLE_MODES = frozenset(
    {
        FacilityMode.EXIT_DELAY,
        FacilityMode.ARMED_AWAY,
        FacilityMode.ARMED_HOME,
        FacilityMode.ENTRY_DELAY,
        FacilityMode.ALARM,
    }
)

# (поточний режим, тригер) -> новий режим. Відсутня пара — недопустимий перехід.
TRANSITIONS: dict[tuple[FacilityMode, ModeTrigger], FacilityMode] = {
    (FacilityMode.DISARMED, ModeTrigger.ARM_AWAY): FacilityMode.EXIT_DELAY,
    (FacilityMode.DISARMED, ModeTrigger.ARM_HOME): FacilityMode.ARMED_HOME,
    (FacilityMode.EXIT_DELAY, ModeTrigger.EXIT_DELAY_EXPIRED): FacilityMode.ARMED_AWAY,
    (FacilityMode.ARMED_AWAY, ModeTrigger.INTRUSION): FacilityMode.ENTRY_DELAY,
    (FacilityMode.ARMED_HOME, ModeTrigger.INTRUSION): FacilityMode.ENTRY_DELAY,
    (FacilityMode.ENTRY_DELAY, ModeTrigger.ENTRY_DELAY_EXPIRED): FacilityMode.ALARM,
    **{(mode, ModeTrigger.DISARM): FacilityMode.DISARMED for mode in DISARMABLE_MODES},
    **{(mode, ModeTrigger.INSTANT_ALARM): FacilityMode.ALARM for mode in FacilityMode},
}

# Стан затримки та стан, у який об'єкт переходить, коли затримка нульова.
_DELAY_SKIP = {
    FacilityMode.EXIT_DELAY: FacilityMode.ARMED_AWAY,
    FacilityMode.ENTRY_DELAY: FacilityMode.ALARM,
}


def next_mode(
    current: FacilityMode, trigger: ModeTrigger, delay_s: int = 0
) -> FacilityMode:
    """Новий режим після тригера.

    delay_s — тривалість затримки, у яку веде перехід (виходу чи входу);
    якщо вона нульова, стан затримки пропускається.
    """
    target = TRANSITIONS.get((current, trigger))
    if target is None:
        raise ConflictError("invalid_transition")
    if target in _DELAY_SKIP and delay_s <= 0:
        return _DELAY_SKIP[target]
    return target


def delay_deadline(
    mode: FacilityMode,
    changed_at: datetime,
    exit_delay_s: int,
    entry_delay_s: int,
) -> datetime | None:
    """Момент завершення поточної затримки або None, якщо затримки немає."""
    if mode == FacilityMode.EXIT_DELAY:
        return changed_at + timedelta(seconds=exit_delay_s)
    if mode == FacilityMode.ENTRY_DELAY:
        return changed_at + timedelta(seconds=entry_delay_s)
    return None


def expired_delay_trigger(
    mode: FacilityMode,
    changed_at: datetime,
    exit_delay_s: int,
    entry_delay_s: int,
    now: datetime,
) -> ModeTrigger | None:
    """Тригер завершення затримки, якщо її час минув на момент now."""
    deadline = delay_deadline(mode, changed_at, exit_delay_s, entry_delay_s)
    if deadline is None or now < deadline:
        return None
    if mode == FacilityMode.EXIT_DELAY:
        return ModeTrigger.EXIT_DELAY_EXPIRED
    return ModeTrigger.ENTRY_DELAY_EXPIRED
