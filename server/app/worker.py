"""Фоновий виконавець таймерів у межах процесу застосунку.

Кожні WORKER_INTERVAL_S секунд викликає process_timers() в окремому
потоці (робота з БД синхронна), а раз на PURGE_INTERVAL_H годин —
очищення застарілих даних. Вимикається змінною WORKER_ENABLED=false.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.db import SessionLocal
from app.services.retention import purge_expired_data
from app.services.timers import process_timers

logger = logging.getLogger("oberih.worker")


def run_once(now: datetime, purge: bool) -> None:
    """Один прохід: таймери та, за потреби, очищення даних."""
    with SessionLocal() as db:
        process_timers(db, now)
        if purge:
            purge_expired_data(db, now)


async def run_worker(stop: asyncio.Event) -> None:
    """Цикл виконавця до сигналу зупинки.

    Помилка одного проходу записується в журнал і не зупиняє цикл.
    """
    purge_every = timedelta(hours=settings.purge_interval_h)
    last_purge: datetime | None = None
    while not stop.is_set():
        now = datetime.now(UTC)
        purge = last_purge is None or now - last_purge >= purge_every
        try:
            await asyncio.to_thread(run_once, now, purge)
            if purge:
                last_purge = now
        except Exception:  # межа фонового циклу: помилку лише журналюємо
            logger.exception("Timer worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_interval_s)
        except TimeoutError:
            continue
