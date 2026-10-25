"""Права ролей на об'єкті (таблиця 7) та обмеження тарифів."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import (
    API,
    add_member,
    create_facility,
    new_user,
    set_tariff,
)


def test_basic_tariff_allows_one_facility(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    response = client.post(f"{API}/facilities", json={"name": "Дача"}, headers=owner)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "tariff_limit"


def test_standard_tariff_allows_three_facilities(
    client: TestClient, db: Session
) -> None:
    headers = new_user(client, "a@test.ua")
    set_tariff(db, "a@test.ua", "standard")
    for _ in range(3):
        create_facility(client, headers)
    listing = client.get(f"{API}/facilities", headers=headers).json()
    assert listing["total"] == 3


def test_stranger_does_not_see_facility(client: TestClient, facility_id: str) -> None:
    stranger = new_user(client, "stranger@test.ua")
    response = client.get(f"{API}/facilities/{facility_id}", headers=stranger)
    assert response.status_code == 404


def test_family_can_view_and_arm_but_not_manage(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    family = new_user(client, "family@test.ua")
    add_member(client, owner, facility_id, "family@test.ua", "family")
    base = f"{API}/facilities/{facility_id}"

    assert client.get(f"{base}/events", headers=family).status_code == 200
    armed = client.post(f"{base}/arm", json={"mode": "home"}, headers=family)
    assert armed.status_code == 200
    zone = client.post(
        f"{base}/zones", json={"name": "Кухня", "zone_type": "interior"}, headers=family
    )
    assert zone.status_code == 403
    assert client.get(f"{base}/members", headers=family).status_code == 403


def test_installer_manages_zones_but_not_events(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    installer = new_user(client, "installer@test.ua")
    add_member(client, owner, facility_id, "installer@test.ua", "installer")
    base = f"{API}/facilities/{facility_id}"

    zone = client.post(
        f"{base}/zones",
        json={"name": "Кухня", "zone_type": "interior"},
        headers=installer,
    )
    assert zone.status_code == 201
    assert client.get(f"{base}/events", headers=installer).status_code == 403
    armed = client.post(f"{base}/arm", json={"mode": "away"}, headers=installer)
    assert armed.status_code == 403


def test_guest_requires_tariff_and_period(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    new_user(client, "guest@test.ua")
    url = f"{API}/facilities/{facility_id}/members"
    until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    body = {"email": "guest@test.ua", "role": "guest", "access_until": until}

    denied = client.post(url, json=body, headers=owner)
    assert denied.json()["error"]["code"] == "tariff_feature"

    set_tariff(db, "owner@test.ua", "standard")
    no_period = client.post(
        url, json={"email": "guest@test.ua", "role": "guest"}, headers=owner
    )
    assert no_period.json()["error"]["code"] == "guest_period_required"
    assert client.post(url, json=body, headers=owner).status_code == 201


def test_guest_access_outside_period_is_denied(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    guest = new_user(client, "guest@test.ua")
    set_tariff(db, "owner@test.ua", "standard")
    now = datetime.now(UTC)
    member = add_member(
        client,
        owner,
        facility_id,
        "guest@test.ua",
        "guest",
        access_from=(now - timedelta(days=2)).isoformat(),
        access_until=(now - timedelta(days=1)).isoformat(),
    )
    response = client.get(f"{API}/facilities/{facility_id}", headers=guest)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "access_expired"

    # Власник продовжує доступ — гість знову бачить об'єкт.
    client.patch(
        f"{API}/facilities/{facility_id}/members/{member['id']}",
        json={"access_until": (now + timedelta(hours=1)).isoformat()},
        headers=owner,
    )
    assert client.get(f"{API}/facilities/{facility_id}", headers=guest).is_success


def test_owner_membership_is_immutable(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    members = client.get(f"{API}/facilities/{facility_id}/members", headers=owner)
    owner_member = members.json()["items"][0]
    assert owner_member["role"] == "owner"
    response = client.delete(
        f"{API}/facilities/{facility_id}/members/{owner_member['id']}", headers=owner
    )
    assert response.json()["error"]["code"] == "owner_immutable"
