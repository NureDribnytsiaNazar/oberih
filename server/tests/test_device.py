"""Події пристроїв: автентифікація вузла, усунення дублікатів, тривоги."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import API, add_member, confirmation, new_user, set_tariff


def _event(channel: int, event_type: str, seq: int) -> dict[str, Any]:
    occurred = datetime.now(UTC) - timedelta(seconds=10 - seq)
    return {
        "channel": channel,
        "event_type": event_type,
        "seq": seq,
        "occurred_at": occurred.isoformat(),
    }


def test_device_requires_valid_token(
    client: TestClient, device: dict[str, Any]
) -> None:
    body = {"events": [_event(1, "opened", 1)]}
    assert client.post(f"{API}/device/events", json=body).status_code == 401
    wrong = {"X-Device-Token": "forged"}
    response = client.post(f"{API}/device/events", json=body, headers=wrong)
    assert response.json()["error"]["code"] == "device_unauthorized"


def test_duplicates_are_ignored(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    batch = {"events": [_event(1, "opened", 1), _event(2, "motion", 2)]}
    first = client.post(f"{API}/device/events", json=batch, headers=device["headers"])
    assert first.json() == {"accepted": 2, "duplicates": 0, "last_seq": 2}

    # Повторне надсилання буфера після відновлення зв'язку.
    resend = {"events": [*batch["events"], _event(1, "closed", 3)]}
    second = client.post(f"{API}/device/events", json=resend, headers=device["headers"])
    assert second.json() == {"accepted": 1, "duplicates": 2, "last_seq": 3}

    events = client.get(f"{API}/facilities/{facility_id}/events", headers=owner)
    assert events.json()["total"] == 3
    interior = client.get(
        f"{API}/facilities/{facility_id}/events",
        params={"zone_id": device["zones"]["interior"]},
        headers=owner,
    )
    assert [e["event_type"] for e in interior.json()["items"]] == ["motion"]


def test_unknown_channel_rejects_whole_batch(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    batch = {"events": [_event(1, "opened", 1), _event(9, "opened", 2)]}
    response = client.post(
        f"{API}/device/events", json=batch, headers=device["headers"]
    )
    assert response.json()["error"]["code"] == "unknown_channel"
    events = client.get(f"{API}/facilities/{facility_id}/events", headers=owner)
    assert events.json()["total"] == 0


def test_server_side_event_types_are_rejected(
    client: TestClient, device: dict[str, Any]
) -> None:
    batch = {"events": [_event(1, "node_offline", 1)]}
    response = client.post(
        f"{API}/device/events", json=batch, headers=device["headers"]
    )
    assert response.status_code == 422


def test_heartbeat_marks_node_online(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    response = client.post(
        f"{API}/device/heartbeat",
        json={"firmware_version": "0.1.0"},
        headers=device["headers"],
    )
    assert response.json()["poll_interval_s"] == 30
    node = client.get(
        f"{API}/facilities/{facility_id}/nodes/{device['node_id']}", headers=owner
    ).json()
    assert node["status"] == "online"
    assert node["firmware_version"] == "0.1.0"


def test_recommission_invalidates_old_token(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    client.post(
        f"{API}/facilities/{facility_id}/nodes/{device['node_id']}/commission",
        headers=owner,
    )
    response = client.post(
        f"{API}/device/heartbeat", json={}, headers=device["headers"]
    )
    assert response.status_code == 401


def test_tamper_raises_confirmed_alarm_and_ack_flow(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    set_tariff(db, "owner@test.ua", "standard")
    guest = new_user(client, "guest@test.ua")
    until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    add_member(client, owner, facility_id, "guest@test.ua", "guest", access_until=until)
    base = f"{API}/facilities/{facility_id}"

    client.post(
        f"{API}/device/events",
        json={"events": [_event(3, "tamper", 1)]},
        headers=device["headers"],
    )
    assert client.get(base, headers=owner).json()["mode"] == "alarm"
    alarms = client.get(f"{base}/alarms", headers=owner).json()
    alarm = alarms["items"][0]
    assert (alarm["level"], alarm["status"]) == ("confirmed", "open")
    assert alarm["zone_id"] == device["zones"]["always_on"]

    # Гість не може ні підтвердити тривогу, ні скинути її зняттям з охорони.
    ack_url = f"{API}/alarms/{alarm['id']}/acknowledge"
    body = {"action": "acknowledge", "confirmation": confirmation()}
    assert client.post(ack_url, json=body, headers=guest).status_code == 403
    guest_disarm = client.post(
        f"{base}/disarm", json={"confirmation": confirmation()}, headers=guest
    )
    assert guest_disarm.status_code == 403

    acked = client.post(ack_url, json=body, headers=owner)
    assert acked.json()["status"] == "acknowledged"
    false_alarm = client.post(
        ack_url,
        json={
            "action": "mark_false",
            "confirmation": confirmation(),
            "comment": "Кіт зачепив корпус",
        },
        headers=owner,
    )
    assert false_alarm.json()["is_false"] is True
    assert false_alarm.json()["status"] == "resolved"
    closed = client.post(ack_url, json=body, headers=owner)
    assert closed.json()["error"]["code"] == "alarm_closed"

    disarmed = client.post(
        f"{base}/disarm", json={"confirmation": confirmation()}, headers=owner
    )
    assert disarmed.json()["mode"] == "disarmed"
