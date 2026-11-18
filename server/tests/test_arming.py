"""Автомат режимів охорони та журнал постановки/зняття."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import ConflictError
from app.models.enums import FacilityMode
from app.services.state_machine import ModeTrigger, next_mode
from tests.conftest import API, confirmation


@pytest.mark.parametrize(
    ("trigger", "delay", "expected"),
    [
        (ModeTrigger.ARM_AWAY, 30, FacilityMode.EXIT_DELAY),
        (ModeTrigger.ARM_AWAY, 0, FacilityMode.ARMED_AWAY),
        (ModeTrigger.ARM_HOME, 30, FacilityMode.ARMED_HOME),
    ],
)
def test_arm_from_disarmed(
    trigger: ModeTrigger, delay: int, expected: FacilityMode
) -> None:
    assert next_mode(FacilityMode.DISARMED, trigger, delay) == expected


@pytest.mark.parametrize(
    "current", [mode for mode in FacilityMode if mode != FacilityMode.DISARMED]
)
def test_cannot_arm_when_not_disarmed(current: FacilityMode) -> None:
    with pytest.raises(ConflictError):
        next_mode(current, ModeTrigger.ARM_AWAY, 30)


def test_arm_disarm_cycle_is_logged(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    base = f"{API}/facilities/{facility_id}"
    armed = client.post(f"{base}/arm", json={"mode": "away"}, headers=owner)
    assert armed.json()["mode"] == "exit_delay"

    again = client.post(f"{base}/arm", json={"mode": "home"}, headers=owner)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"

    no_confirm = client.post(f"{base}/disarm", json={}, headers=owner)
    assert no_confirm.json()["error"]["code"] == "reauth_required"
    wrong = client.post(
        f"{base}/disarm",
        json={"confirmation": {"method": "password", "value": "wrong"}},
        headers=owner,
    )
    assert wrong.json()["error"]["code"] == "reauth_failed"

    disarmed = client.post(
        f"{base}/disarm",
        json={"confirmation": confirmation(), "source": "mobile"},
        headers=owner,
    )
    assert disarmed.json()["mode"] == "disarmed"

    log = client.get(f"{base}/arming-log", headers=owner).json()
    assert log["total"] == 2
    latest = log["items"][0]
    assert (latest["from_mode"], latest["to_mode"]) == ("exit_delay", "disarmed")
    assert latest["source"] == "mobile"
    assert latest["auth_method"] == "password"
    assert latest["user_id"] is not None


def test_disarm_when_already_disarmed_is_rejected(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    response = client.post(
        f"{API}/facilities/{facility_id}/disarm",
        json={"confirmation": confirmation()},
        headers=owner,
    )
    assert response.status_code == 409


def test_exit_delay_expires_into_armed_away(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    base = f"{API}/facilities/{facility_id}"
    client.post(f"{base}/arm", json={"mode": "away"}, headers=owner)
    # Імітуємо, що затримка виходу (30 с) уже минула.
    db.execute(
        text(
            "UPDATE facilities SET mode_changed_at = now() - interval '1 minute' "
            "WHERE id = :id"
        ),
        {"id": facility_id},
    )
    db.commit()

    facility = client.get(base, headers=owner).json()
    assert facility["mode"] == "armed_away"
    latest = client.get(f"{base}/arming-log", headers=owner).json()["items"][0]
    assert latest["source"] == "system"
    assert latest["user_id"] is None


def test_zero_exit_delay_arms_immediately(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    base = f"{API}/facilities/{facility_id}"
    settings = client.put(f"{base}/settings", json={"exit_delay_s": 0}, headers=owner)
    assert settings.json()["exit_delay_s"] == 0
    armed = client.post(f"{base}/arm", json={"mode": "away"}, headers=owner)
    assert armed.json()["mode"] == "armed_away"


def test_settings_reject_inverted_thresholds(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    response = client.put(
        f"{API}/facilities/{facility_id}/settings",
        json={"alarm_threshold": "0.95"},
        headers=owner,
    )
    assert response.json()["error"]["code"] == "invalid_thresholds"
