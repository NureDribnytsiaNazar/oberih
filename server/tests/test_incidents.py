"""Стисла хронологія інциденту: факти, припущення, мінімізація даних."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from tests.conftest import API, set_tariff


def raise_alarm(
    client: TestClient, device: dict[str, Any], owner: dict[str, str], facility_id: str
) -> str:
    """Відчинення дверей і рух під охороною дають тривогу з двома подіями."""
    base = f"{API}/facilities/{facility_id}"
    client.put(f"{base}/settings", json={"exit_delay_s": 0}, headers=owner)
    client.post(f"{base}/arm", json={"mode": "away"}, headers=owner)
    now = datetime.now(UTC)
    events = [
        {
            "channel": 1,
            "event_type": "opened",
            "seq": 1,
            "occurred_at": now.isoformat(),
        },
        {
            "channel": 2,
            "event_type": "motion",
            "seq": 2,
            "occurred_at": (now + timedelta(seconds=10)).isoformat(),
        },
    ]
    client.post(
        f"{API}/device/events", json={"events": events}, headers=device["headers"]
    )
    return str(client.get(f"{base}/alarms", headers=owner).json()["items"][0]["id"])


def test_summary_separates_facts_and_assumptions(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    set_tariff(db, "owner@test.ua", "professional")
    alarm_id = raise_alarm(client, device, owner, facility_id)
    summary = client.post(f"{API}/alarms/{alarm_id}/summary", headers=owner).json()

    facts = summary["facts"].splitlines()
    assert len(facts) == 2
    assert all(line.startswith("[подія №") for line in facts)
    assert "«Вхідні двері»: Відчинено" in facts[0]
    assert summary["assumptions"].startswith("Імовірне проникнення")
    assert summary["model_name"] == "template-v1"
    # Мінімізація даних: у тексті немає пошти чи імені користувача.
    assert "owner" not in summary["facts"] + summary["assumptions"]

    english = client.post(
        f"{API}/alarms/{alarm_id}/summary", headers={**owner, "Accept-Language": "en"}
    ).json()
    assert english["facts"].startswith("[event #")
    listing = client.get(f"{API}/alarms/{alarm_id}/summaries", headers=owner).json()
    assert len(listing) == 2


def test_summary_requires_professional_tariff(
    client: TestClient, owner: dict[str, str], facility_id: str, device: dict[str, Any]
) -> None:
    alarm_id = raise_alarm(client, device, owner, facility_id)
    response = client.post(f"{API}/alarms/{alarm_id}/summary", headers=owner)
    assert response.json()["error"]["code"] == "tariff_feature"


def test_external_provider_stub_is_unavailable(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_tariff(db, "owner@test.ua", "professional")
    alarm_id = raise_alarm(client, device, owner, facility_id)
    monkeypatch.setattr(settings, "summary_provider", "external")
    response = client.post(f"{API}/alarms/{alarm_id}/summary", headers=owner)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
