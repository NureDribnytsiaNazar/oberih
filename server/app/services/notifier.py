"""Сповіщення користувачів про тривоги (ФМ-8).

Доставка push-повідомлень і електронної пошти не входить у ЛБ3, тому є
лише інтерфейс Notifier і реалізація, що записує сповіщення в журнал
застосунку. Справжні канали доставки додаються новою реалізацією без
змін у конвеєрі.
"""

import logging
from typing import Protocol

from app.models.events import Alarm

logger = logging.getLogger("oberih.notifications")


class Notifier(Protocol):
    """Канал доставки сповіщень про тривоги."""

    def alarm_changed(self, alarm: Alarm) -> None:
        """Повідомляє про нову тривогу або підвищення її рівня."""


class LogNotifier:
    """Заглушка: записує сповіщення в журнал застосунку."""

    def alarm_changed(self, alarm: Alarm) -> None:
        """Записує рівень тривоги та об'єкт (без персональних даних)."""
        logger.info(
            "alarm %s facility=%s level=%s",
            alarm.id,
            alarm.facility_id,
            alarm.level.value,
        )


notifier: Notifier = LogNotifier()
