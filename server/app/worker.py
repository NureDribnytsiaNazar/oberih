"""Фоновий виконавець таймерів у межах процесу застосунку.

Кожні WORKER_INTERVAL_S секунд викликає process_timers() в окремому
потоці (робота з БД синхронна), а раз на PURGE_INTERVAL_H годин —
очищення застарілих даних. Вимикається змінною WORKER_ENABLED=false.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.services.retention import purge_expired_data
from app.services.timers import process_timers

logger = logging.getLogger("oberih.worker")
# Ключ рекомендаційного блокування PostgreSQL для проходу таймерів.
TIMERS_LOCK_KEY = 0x0BE21C


def run_once(db: Session, now: datetime, purge: bool) -> bool:
    """Один прохід: таймери та, за потреби, очищення даних.

    Прохід виконується під pg_try_advisory_xact_lock: якщо запущено кілька
    екземплярів api, таймери й очищення даних виконає лише той, хто отримав
    блокування (воно знімається під час фіксації транзакції в
    process_timers). Повертає False, якщо прохід пропущено.
    """
    locked = db.scalar(select(func.pg_try_advisory_xact_lock(TIMERS_LOCK_KEY)))
    if not locked:
        db.rollback()
        return False
    process_timers(db, now)
    if purge:
        purge_expired_data(db, now)
    return True


def _run_once_in_session(now: datetime, purge: bool) -> None:
    with SessionLocal() as db:
        run_once(db, now, purge)


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
            await asyncio.to_thread(_run_once_in_session, now, purge)
            if purge:
                last_purge = now
        except Exception:  # межа фонового циклу: помилку лише журналюємо
            logger.exception("Timer worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_interval_s)
        except TimeoutError:
            continue
