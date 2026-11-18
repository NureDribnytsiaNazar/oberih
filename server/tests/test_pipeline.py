"""Конвеєр подій через API: тривоги, затримка входу, таймери, вузли."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.timers import process_timers
from tests.conftest import API, confirmation

REED, PIR, TAMPER = 1, 2, 3


def send(
    client: TestClient,
    device: dict[str, Any],
    *events: tuple[int, str, int, datetime],
) -> dict[str, Any]:
    """Надсилає пакет подій (канал, тип, seq, час) від імені вузла."""
    body = {
        "events": [
            {"channel": ch, "event_type": et, "seq": seq, "occurred_at": t.isoformat()}
            for ch, et, seq, t in events
        ]
    }
    response = client.post(f"{API}/device/events", json=body, headers=device["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def arm(client: TestClient, owner: dict[str, str], facility_id: str, mode: str) -> None:
    """Ставить об'єкт під охорону без затримки виходу."""
    base = f"{API}/facilities/{facility_id}"
    client.put(f"{base}/settings", json={"exit_delay_s": 0}, headers=owner)
    response = client.post(f"{base}/arm", json={"mode": mode}, headers=owner)
    assert response.json()["mode"] == f"armed_{mode}"


def state(client: TestClient, owner: dict[str, str], facility_id: str) -> str:
    return str(
        client.get(f"{API}/facilities/{facility_id}", headers=owner).json()["mode"]
    )


def alarms(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> list[dict[str, Any]]:
    url = f"{API}/facilities/{facility_id}/alarms"
    return list(client.get(url, headers=owner).json()["items"])


def test_disarmed_facility_only_archives_perimeter_events(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    now = datetime.now(UTC)
    send(client, device, (REED, "opened", 1, now), (PIR, "motion", 2, now))
    assert alarms(client, owner, facility_id) == []
    assert state(client, owner, facility_id) == "disarmed"


def test_intrusion_entry_delay_then_confirmed_same_alarm(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    arm(client, owner, facility_id, "away")
    now = datetime.now(UTC)
    send(client, device, (REED, "opened", 1, now))
    assert state(client, owner, facility_id) == "entry_delay"
    [alarm] = alarms(client, owner, facility_id)
    assert (alarm["level"], alarm["confidence"]) == ("alarm", "0.50")

    send(client, device, (PIR, "motion", 2, now + timedelta(seconds=20)))
    [alarm] = alarms(client, owner, facility_id)
    assert (alarm["level"], alarm["confidence"]) == ("confirmed", "0.90")


def test_entry_delay_expires_into_alarm_by_timer(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    arm(client, owner, facility_id, "away")
    send(client, device, (REED, "opened", 1, datetime.now(UTC)))

    early = process_timers(db, datetime.now(UTC) + timedelta(seconds=10))
    assert early.alarms == 0
    report = process_timers(db, datetime.now(UTC) + timedelta(seconds=31))
    assert report.alarms == 1
    assert state(client, owner, facility_id) == "alarm"
    log = client.get(f"{API}/facilities/{facility_id}/arming-log", headers=owner)
    latest = log.json()["items"][0]
    assert (latest["to_mode"], latest["source"]) == ("alarm", "system")


def test_disarm_during_entry_delay_cancels_alarm(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    arm(client, owner, facility_id, "away")
    send(client, device, (REED, "opened", 1, datetime.now(UTC)))
    response = client.post(
        f"{API}/facilities/{facility_id}/disarm",
        json={"confirmation": confirmation()},
        headers=owner,
    )
    assert response.json()["mode"] == "disarmed"
    [alarm] = alarms(client, owner, facility_id)
    assert alarm["status"] == "cancelled"


def test_home_mode_pir_ignored_reed_triggers_entry_delay(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    arm(client, owner, facility_id, "home")
    now = datetime.now(UTC)
    send(client, device, (PIR, "motion", 1, now))
    assert alarms(client, owner, facility_id) == []
    assert state(client, owner, facility_id) == "armed_home"
    send(client, device, (REED, "opened", 2, now + timedelta(seconds=1)))
    assert state(client, owner, facility_id) == "entry_delay"


def test_tamper_raises_alarm_while_disarmed(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    send(client, device, (TAMPER, "tamper", 1, datetime.now(UTC)))
    assert state(client, owner, facility_id) == "alarm"
    [alarm] = alarms(client, owner, facility_id)
    assert alarm["level"] == "confirmed"


def test_window_duplicates_through_api(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    now = datetime.now(UTC) - timedelta(minutes=1)
    result = send(
        client,
        device,
        (REED, "opened", 1, now),
        (REED, "opened", 2, now + timedelta(seconds=4.9)),
        (REED, "opened", 3, now + timedelta(seconds=10.0)),
    )
    statuses = [item["status"] for item in result["results"]]
    assert statuses == ["accepted", "duplicate", "accepted"]
    # Повторне надсилання буфера після відновлення зв'язку.
    again = send(client, device, (REED, "opened", 3, now + timedelta(seconds=10)))
    assert again["duplicates"] == 1


def test_node_goes_offline_once_and_back_online(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    client.post(f"{API}/device/heartbeat", json={}, headers=device["headers"])
    start = datetime.now(UTC)

    assert process_timers(db, start + timedelta(seconds=89)).offline_nodes == 0
    assert process_timers(db, start + timedelta(seconds=91)).offline_nodes == 1
    assert process_timers(db, start + timedelta(seconds=200)).offline_nodes == 0
    node_url = f"{API}/facilities/{facility_id}/nodes/{device['node_id']}"
    assert client.get(node_url, headers=owner).json()["status"] == "offline"

    client.post(f"{API}/device/heartbeat", json={}, headers=device["headers"])
    assert client.get(node_url, headers=owner).json()["status"] == "online"
    types = db.scalars(
        text("SELECT event_type FROM events WHERE sensor_id IS NULL ORDER BY id")
    ).all()
    assert types == ["node_offline", "node_online"]


def test_exit_delay_finished_by_timer(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    base = f"{API}/facilities/{facility_id}"
    client.post(f"{base}/arm", json={"mode": "away"}, headers=owner)
    report = process_timers(db, datetime.now(UTC) + timedelta(seconds=31))
    assert report.armed == 1
    db.expire_all()
    mode = db.scalar(
        text("SELECT mode FROM facilities WHERE id = :id"), {"id": facility_id}
    )
    assert mode == "armed_away"
