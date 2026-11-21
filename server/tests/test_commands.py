"""Команди сервера для вузла (ІК-7) і конфігурація вузла (ІК-8)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.devices import Node, NodeCommand
from app.models.enums import CommandStatus, FacilityMode
from app.schemas.events import HeartbeatIn
from app.services import commands, device as device_service
from tests.conftest import API, confirmation


def _heartbeat(
    client: TestClient, device: dict[str, Any], **body: Any
) -> dict[str, Any]:
    response = client.post(
        f"{API}/device/heartbeat", json=body, headers=device["headers"]
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _arm(client: TestClient, owner: dict[str, str], facility_id: str) -> None:
    response = client.post(
        f"{API}/facilities/{facility_id}/arm", json={"mode": "home"}, headers=owner
    )
    assert response.status_code == 200, response.text


def _signing_string(node_id: str, command: dict[str, Any]) -> str:
    """Рядок підпису так, як його будує вузол (iot/src/command_verifier.cpp)."""
    return "|".join(
        (
            node_id,
            str(command["nonce"]),
            command["type"],
            command["payload"],
            str(command["issued_at"]),
        )
    )


def test_commission_returns_command_key(device: dict[str, Any]) -> None:
    key = device["command_key"]
    assert len(key) == 64
    bytes.fromhex(key)


def test_arm_queues_signed_command(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    body = _heartbeat(client, device)

    assert body["facility_mode"] == "armed_home"
    [command] = body["commands"]
    assert command["type"] == "arm_home"
    assert command["payload"] == '{"mode":"armed_home"}'
    assert command["expires_at"] - command["issued_at"] == 60
    key = bytes.fromhex(device["command_key"])
    message = _signing_string(device["node_id"], command)
    assert commands.verify(key, message, command["signature"])


def test_tampered_command_fails_verification(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    [command] = _heartbeat(client, device)["commands"]
    key = bytes.fromhex(device["command_key"])

    forged = {**command, "payload": '{"mode":"disarmed"}'}
    assert not commands.verify(
        key, _signing_string(device["node_id"], forged), command["signature"]
    )
    wrong_key = bytes(32)
    message = _signing_string(device["node_id"], command)
    assert not commands.verify(wrong_key, message, command["signature"])


def test_command_redelivered_until_ack(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    first = _heartbeat(client, device)["commands"]
    again = _heartbeat(client, device)["commands"]
    assert [c["id"] for c in again] == [c["id"] for c in first]

    acked = _heartbeat(client, device, acked_command_ids=[first[0]["id"]])
    assert acked["commands"] == []
    assert _heartbeat(client, device)["commands"] == []


def test_expired_command_is_not_delivered(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    node = db.get_one(Node, uuid.UUID(device["node_id"]))
    later = datetime.now(UTC) + commands.COMMAND_TTL + timedelta(seconds=1)

    result = device_service.heartbeat(db, node, HeartbeatIn(), now=later)

    assert result.commands == []
    stored = db.scalars(select(NodeCommand)).one()
    assert stored.status == CommandStatus.EXPIRED


def test_nonce_strictly_increases(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    response = client.post(
        f"{API}/facilities/{facility_id}/disarm",
        json={"confirmation": confirmation()},
        headers=owner,
    )
    assert response.status_code == 200, response.text

    sent = _heartbeat(client, device)["commands"]
    assert [c["type"] for c in sent] == ["arm_home", "disarm"]
    assert sent[0]["nonce"] < sent[1]["nonce"]


def test_node_does_not_receive_or_ack_foreign_commands(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    second_device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    [own] = _heartbeat(client, device)["commands"]

    # Вузол іншого об'єкта не бачить і не може підтвердити чужу команду.
    other = _heartbeat(client, second_device, acked_command_ids=[own["id"]])
    assert other["commands"] == []
    assert [c["id"] for c in _heartbeat(client, device)["commands"]] == [own["id"]]


def test_node_settings_bump_config_version(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    url = f"{API}/facilities/{facility_id}/nodes/{device['node_id']}"
    response = client.patch(url, json={"debounce_ms": 80}, headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["config_version"] == 2

    body = _heartbeat(client, device)
    assert body["config"]["debounce_ms"] == 80
    assert body["config"]["config_version"] == 2
    [command] = body["commands"]
    assert command["type"] == "set_config"
    assert '"debounce_ms":80' in command["payload"]

    # Перейменування не змінює конфігурації вузла.
    renamed = client.patch(url, json={"name": "Передпокій"}, headers=owner)
    assert renamed.json()["config_version"] == 2


def test_node_settings_bounds(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    url = f"{API}/facilities/{facility_id}/nodes/{device['node_id']}"
    assert client.patch(url, json={"debounce_ms": 5}, headers=owner).status_code == 422
    too_long = {"pir_lockout_s": 601}
    assert client.patch(url, json=too_long, headers=owner).status_code == 422


def test_facility_settings_bump_config_version(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    url = f"{API}/facilities/{facility_id}/settings"
    client.put(url, json={"far_window_days": 10}, headers=owner)
    assert _heartbeat(client, device)["config"]["config_version"] == 1

    client.put(url, json={"exit_delay_s": 20}, headers=owner)
    body = _heartbeat(client, device)
    assert body["config"]["exit_delay_s"] == 20
    assert body["config"]["config_version"] == 2


def test_old_heartbeat_is_compatible(
    client: TestClient, device: dict[str, Any]
) -> None:
    empty = _heartbeat(client, device)
    assert empty["facility_mode"] == "disarmed"
    assert {"server_time", "poll_interval_s", "facility_mode"} <= empty.keys()
    old = _heartbeat(client, device, firmware_version="0.1.0")
    assert old["poll_interval_s"] == 30


def test_mode_reconciled_after_offline_work(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    [queued] = _heartbeat(client, device)["commands"]
    _heartbeat(client, device, acked_command_ids=[queued["id"]])

    # У буфері ще є події: розбіжність може бути недоставленою тривогою.
    busy = _heartbeat(client, device, mode="disarmed", buffer_depth=2)
    assert busy["commands"] == []

    synced = _heartbeat(client, device, mode="disarmed", buffer_depth=0)
    [command] = synced["commands"]
    assert command["type"] == "arm_home"
    # Поки команда відкрита, нова не створюється.
    repeat = _heartbeat(client, device, mode="disarmed", buffer_depth=0)
    assert [c["id"] for c in repeat["commands"]] == [command["id"]]


def test_reconcile_ignores_equivalent_modes() -> None:
    expected = commands.EQUIVALENT_MODES[FacilityMode.ARMED_AWAY]
    assert FacilityMode.EXIT_DELAY in expected
    assert FacilityMode.ALARM not in commands.EQUIVALENT_MODES


def test_owner_sees_command_queue(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    _arm(client, owner, facility_id)
    url = f"{API}/facilities/{facility_id}/nodes/{device['node_id']}/commands"
    [command] = client.get(url, headers=owner).json()
    assert command["status"] == "pending"
    _heartbeat(client, device)
    assert client.get(url, headers=owner).json()[0]["status"] == "delivered"
