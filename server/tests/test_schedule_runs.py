"""Виконання розкладів постановки й зняття фоновим виконавцем."""

import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.devices import NodeCommand
from app.models.enums import ActionSource, FacilityMode
from app.models.events import ArmingLogEntry
from app.models.facilities import Facility
from app.services.schedules import CATCH_UP_WINDOW, due_moment
from app.services.timers import process_timers
from tests.conftest import API

KYIV = "Europe/Kyiv"
ALL_DAYS = 0b1111111
# 23.11.2026 — понеділок; 07:00 UTC = 09:00 за Києвом (зимовий час, UTC+2).
MONDAY_0900_KYIV = datetime(2026, 11, 23, 7, 0, tzinfo=UTC)
NINE = time(9, 0)


def test_due_at_local_time_in_facility_timezone() -> None:
    moment = due_moment(NINE, ALL_DAYS, KYIV, None, MONDAY_0900_KYIV)
    assert moment is not None
    assert moment.astimezone(UTC) == MONDAY_0900_KYIV


def test_not_due_before_time_or_on_other_day() -> None:
    early = MONDAY_0900_KYIV - timedelta(minutes=1)
    assert due_moment(NINE, ALL_DAYS, KYIV, None, early) is None
    weekend_only = 0b1100000  # субота й неділя
    assert due_moment(NINE, weekend_only, KYIV, None, MONDAY_0900_KYIV) is None


def test_catch_up_window_and_single_run() -> None:
    late = MONDAY_0900_KYIV + CATCH_UP_WINDOW
    assert due_moment(NINE, ALL_DAYS, KYIV, None, late) is not None
    too_late = late + timedelta(seconds=1)
    assert due_moment(NINE, ALL_DAYS, KYIV, None, too_late) is None
    # Уже виконаний запуск не повторюється.
    assert due_moment(NINE, ALL_DAYS, KYIV, MONDAY_0900_KYIV, late) is None


def test_run_just_after_midnight_belongs_to_previous_day() -> None:
    # Розклад на 23:58 у неділю, прохід о 00:03 у понеділок.
    sunday = 1 << 6
    now = datetime(2026, 11, 22, 22, 3, tzinfo=UTC)  # 00:03 понеділка за Києвом
    moment = due_moment(time(23, 58), sunday, KYIV, None, now)
    assert moment is not None and moment.weekday() == 6


def _schedule(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    action: str,
) -> None:
    body = {
        "name": f"Розклад {action}",
        "action": action,
        "days_mask": ALL_DAYS,
        "local_time": "09:00:00",
    }
    response = client.post(
        f"{API}/facilities/{facility_id}/schedules", json=body, headers=owner
    )
    assert response.status_code == 201, response.text


def test_schedule_arms_facility_and_commands_node(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _schedule(client, owner, facility_id, "arm_away")

    report = process_timers(db, MONDAY_0900_KYIV)

    assert report.schedules == 1
    facility = db.get_one(Facility, uuid.UUID(facility_id))
    assert facility.mode == FacilityMode.EXIT_DELAY
    entry = db.scalars(select(ArmingLogEntry)).one()
    assert entry.source == ActionSource.SCHEDULE
    command = db.scalars(select(NodeCommand)).one()
    assert command.command_type.value == "arm_away"

    # Наступний прохід у межах вікна того самого запуску нічого не робить.
    again = process_timers(db, MONDAY_0900_KYIV + timedelta(seconds=5))
    assert again.schedules == 0
    assert len(db.scalars(select(ArmingLogEntry)).all()) == 1


def test_schedule_does_not_disarm_during_alarm(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
) -> None:
    facility = db.get_one(Facility, uuid.UUID(facility_id))
    facility.mode = FacilityMode.ALARM
    db.commit()
    _schedule(client, owner, facility_id, "disarm")

    report = process_timers(db, MONDAY_0900_KYIV)

    assert report.schedules == 0
    db.refresh(facility)
    assert facility.mode == FacilityMode.ALARM


def test_arm_schedule_when_already_armed_is_skipped(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
) -> None:
    facility = db.get_one(Facility, uuid.UUID(facility_id))
    facility.mode = FacilityMode.ARMED_HOME
    db.commit()
    _schedule(client, owner, facility_id, "arm_away")

    assert process_timers(db, MONDAY_0900_KYIV).schedules == 0
    db.refresh(facility)
    assert facility.mode == FacilityMode.ARMED_HOME
