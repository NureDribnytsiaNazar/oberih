"""Статистика хибних спрацювань і відтворення тестових сценаріїв."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.devices import Sensor
from app.models.enums import AlarmLevel, AlarmStatus, EventType
from app.models.events import Alarm, AlarmEvent, Event
from tests.conftest import API, add_member, new_user, set_tariff

REED, PIR = 1, 2


def sensor_id(db: Session, device: dict[str, Any], channel: int) -> uuid.UUID:
    return db.scalars(
        select(Sensor.id).where(
            Sensor.node_id == uuid.UUID(device["node_id"]), Sensor.channel == channel
        )
    ).one()


def add_alarms(
    db: Session,
    facility_id: str,
    device: dict[str, Any],
    channel: int,
    total: int,
    false: int,
    opened_at: datetime | None = None,
    status: AlarmStatus = AlarmStatus.RESOLVED,
) -> None:
    """Створює total закритих тривог датчика, з них false — хибні."""
    sensor = sensor_id(db, device, channel)
    start = db.scalar(select(func.coalesce(func.max(Event.seq), 0))) or 0
    for index in range(total):
        event = Event(
            facility_id=uuid.UUID(facility_id),
            node_id=uuid.UUID(device["node_id"]),
            sensor_id=sensor,
            event_type=EventType.OPENED,
            seq=start + index + 1,
            occurred_at=opened_at or datetime.now(UTC),
        )
        alarm = Alarm(
            facility_id=uuid.UUID(facility_id),
            zone_id=uuid.UUID(device["zones"]["perimeter"]),
            level=AlarmLevel.ALARM,
            status=status,
            confidence=Decimal("0.5"),
            is_false=index < false,
            opened_at=opened_at or datetime.now(UTC),
        )
        db.add_all([event, alarm])
        db.flush()
        db.add(AlarmEvent(alarm_id=alarm.id, event_id=event.id))
    db.commit()


def stats(
    client: TestClient, owner: dict[str, str], facility_id: str, **params: str
) -> dict[str, Any]:
    url = f"{API}/facilities/{facility_id}/statistics/false-alarms"
    response = client.get(url, headers=owner, params=params)
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.fixture()
def standard(db: Session, owner: dict[str, str]) -> None:
    set_tariff(db, "owner@test.ua", "standard")


@pytest.mark.parametrize(
    ("total", "false", "far", "recommended"),
    [
        (4, 4, "1.00", False),  # N < 5 — замало даних
        (5, 2, "0.40", True),  # N = 5, FAR = 0,4 > 0,3
        (10, 3, "0.30", False),  # FAR = 0,3 — не строго більше порога
    ],
)
def test_far_recommendation_rules(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    standard: None,
    total: int,
    false: int,
    far: str,
    recommended: bool,
) -> None:
    add_alarms(db, facility_id, device, REED, total, false)
    [row] = stats(client, owner, facility_id)["sensors"]
    assert (row["alarms"], row["false_alarms"], row["far"]) == (total, false, far)
    assert (row["recommendation"] == "check_sensor") is recommended


def test_far_window_and_cancelled_alarms_excluded(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    standard: None,
) -> None:
    old = datetime.now(UTC) - timedelta(days=31)
    add_alarms(db, facility_id, device, REED, 3, 3, opened_at=old)
    add_alarms(db, facility_id, device, REED, 2, 0, status=AlarmStatus.CANCELLED)
    add_alarms(db, facility_id, device, PIR, 1, 1)
    body = stats(client, owner, facility_id)
    assert [row["sensor_name"] for row in body["sensors"]] == ["pir"]
    assert body["zones"][0]["alarms"] == 1


def test_far_recommendation_text_is_localized(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    standard: None,
) -> None:
    add_alarms(db, facility_id, device, REED, 5, 5)
    url = f"{API}/facilities/{facility_id}/statistics/false-alarms"
    en = client.get(url, headers={**owner, "Accept-Language": "en"}).json()
    uk = client.get(url, headers=owner).json()
    assert en["sensors"][0]["recommendation_text"].startswith("The false alarm rate")
    assert uk["sensors"][0]["recommendation_text"].startswith("Частка хибних")


def test_far_by_hour_uses_local_time(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    standard: None,
) -> None:
    # 2026-10-25: перехід на зимовий час у Києві (UTC+3 -> UTC+2).
    before = datetime(2026, 10, 24, 22, 30, tzinfo=UTC)  # 01:30 за Києвом
    after = datetime(2026, 10, 25, 22, 30, tzinfo=UTC)  # 00:30 за Києвом
    client.put(
        f"{API}/facilities/{facility_id}/settings",
        json={"far_window_days": 365},
        headers=owner,
    )
    add_alarms(db, facility_id, device, REED, 1, 0, opened_at=before)
    add_alarms(db, facility_id, device, REED, 1, 0, opened_at=after)
    hours = stats(client, owner, facility_id, tz="Europe/Kyiv")["hours"]
    assert sorted(item["key"] for item in hours) == ["0", "1"]


def test_far_requires_tariff_and_valid_tz(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    url = f"{API}/facilities/{facility_id}/statistics/false-alarms"
    response = client.get(url, headers=owner)
    assert response.json()["error"]["code"] == "tariff_feature"


# --- Сценарії ----------------------------------------------------------------


def create_scenario(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    steps: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> str:
    response = client.post(
        f"{API}/facilities/{facility_id}/scenarios",
        json={"name": "Проникнення", "steps": steps, "expected": expected},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def run(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    scenario: str,
    mode: str = "armed_away",
) -> dict[str, Any]:
    url = f"{API}/facilities/{facility_id}/scenarios/{scenario}/run"
    response = client.post(url, json={"mode": mode}, headers=owner)
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_scenario_replay_is_isolated_and_passes(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    steps = [
        {
            "offset_ms": 0,
            "sensor_id": str(sensor_id(db, device, REED)),
            "state": "opened",
        },
        {
            "offset_ms": 20000,
            "sensor_id": str(sensor_id(db, device, PIR)),
            "state": "motion",
        },
    ]
    scenario = create_scenario(
        client, owner, facility_id, steps, [{"level": "confirmed"}]
    )
    result = run(client, owner, facility_id, scenario)
    assert result["passed"] is True
    assert result["actual"] == [
        {"level": "confirmed", "zone_id": device["zones"]["perimeter"]}
    ]
    # Відтворення не створює реальних подій і тривог.
    assert db.scalar(select(func.count()).select_from(Event)) == 0
    assert db.scalar(select(func.count()).select_from(Alarm)) == 0
    runs = client.get(
        f"{API}/facilities/{facility_id}/scenarios/{scenario}/runs", headers=owner
    )
    assert runs.json()["total"] == 1


def test_scenario_mismatch_fails(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    steps = [
        {
            "offset_ms": 0,
            "sensor_id": str(sensor_id(db, device, PIR)),
            "state": "motion",
        }
    ]
    scenario = create_scenario(
        client, owner, facility_id, steps, [{"level": "confirmed"}]
    )
    # У режимі «Вдома» рух не обробляється: очікувана тривога не виникає.
    result = run(client, owner, facility_id, scenario, mode="armed_home")
    assert result["passed"] is False
    assert result["mismatches"] == [
        {"kind": "missing", "expected": {"level": "confirmed", "zone_id": None}}
    ]


def test_scenario_rejects_foreign_sensor_and_family_role(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    url = f"{API}/facilities/{facility_id}/scenarios"
    foreign = {"offset_ms": 0, "sensor_id": str(uuid.uuid4()), "state": "opened"}
    response = client.post(url, json={"name": "x", "steps": [foreign]}, headers=owner)
    assert response.json()["error"]["code"] == "scenario_sensor_missing"

    family = new_user(client, "family@test.ua")
    add_member(client, owner, facility_id, "family@test.ua", "family")
    assert client.get(url, headers=family).status_code == 403
