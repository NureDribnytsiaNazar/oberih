"""Таймери: затримки виходу й входу, розклади, недоступність вузлів, сертифікати.

process_timers() — єдина синхронна функція, яку фоновий виконавець
викликає кожні WORKER_INTERVAL_S секунд. Годинник передається параметром
now, тому тести перевіряють таймери без очікування.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import FacilityMode
from app.models.facilities import Facility
from app.services import arming, certificates, nodes, schedules
from app.services.state_machine import ModeTrigger

DELAY_MODES = (FacilityMode.EXIT_DELAY, FacilityMode.ENTRY_DELAY)


@dataclass
class TimerReport:
    """Скільки змін виконано за один прохід."""

    armed: int = 0  # exit_delay -> armed_away
    alarms: int = 0  # entry_delay -> alarm
    offline_nodes: int = 0
    expired_certificates: int = 0
    schedules: int = 0  # змін режиму за розкладом


def process_timers(db: Session, now: datetime) -> TimerReport:
    """Один прохід фонового виконавця; фіксує транзакцію."""
    report = TimerReport()
    facilities = db.scalars(select(Facility).where(Facility.mode.in_(DELAY_MODES)))
    for facility in facilities:
        trigger = arming.apply_due_timer(db, facility, now)
        if trigger == ModeTrigger.EXIT_DELAY_EXPIRED:
            report.armed += 1
        elif trigger == ModeTrigger.ENTRY_DELAY_EXPIRED:
            report.alarms += 1
    report.schedules = schedules.run_due_schedules(db, now)
    report.offline_nodes = nodes.detect_offline(db, now)
    report.expired_certificates = certificates.mark_expired(db, now)
    db.commit()
    return report
