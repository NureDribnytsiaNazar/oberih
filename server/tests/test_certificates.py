"""Сертифікати вузлів: випуск, відкликання, поновлення, прострочення."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography import x509
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.certificates import create_ca
from app.services.timers import process_timers
from tests.conftest import API, confirmation
from tests.test_admin import make_admin

URL = f"{API}/admin/certificates"


@pytest.fixture()
def ca_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "ca"
    monkeypatch.setattr(settings, "ca_dir", directory)
    return directory


@pytest.fixture()
def admin(client: TestClient, db: Session, owner: dict[str, str]) -> dict[str, str]:
    make_admin(db, "owner@test.ua")
    return owner


def issue(
    client: TestClient, admin: dict[str, str], node_id: str, days: int = 365
) -> dict[str, Any]:
    response = client.post(URL, json={"node_id": node_id, "days": days}, headers=admin)
    assert response.status_code == 201, response.text
    return dict(response.json())


def heartbeat(client: TestClient, device: dict[str, Any]) -> Any:
    return client.post(f"{API}/device/heartbeat", json={}, headers=device["headers"])


def test_issue_requires_initialized_ca(
    client: TestClient, admin: dict[str, str], device: dict[str, Any], ca_dir: Path
) -> None:
    response = client.post(URL, json={"node_id": device["node_id"]}, headers=admin)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ca_not_initialized"


def test_issue_returns_key_once_and_is_signed_by_ca(
    client: TestClient, admin: dict[str, str], device: dict[str, Any], ca_dir: Path
) -> None:
    ca_cert_path = create_ca(ca_dir)
    issued = issue(client, admin, device["node_id"])
    assert "PRIVATE KEY" in issued["private_key_pem"]

    cert = x509.load_pem_x509_certificate(issued["certificate"]["pem"].encode())
    ca = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
    cert.verify_directly_issued_by(ca)
    stored = client.get(f"{URL}/{issued['certificate']['id']}", headers=admin).json()
    assert "private_key_pem" not in stored
    assert heartbeat(client, device).status_code == 200


def test_revoked_certificate_fails_node_auth(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    device: dict[str, Any],
    ca_dir: Path,
) -> None:
    create_ca(ca_dir)
    cert = issue(client, admin, device["node_id"])["certificate"]
    revoke_url = f"{URL}/{cert['id']}/revoke"
    assert client.post(revoke_url, json={}, headers=admin).status_code == 401
    revoked = client.post(
        revoke_url, json={"confirmation": confirmation()}, headers=admin
    )
    assert revoked.json()["status"] == "revoked"

    response = heartbeat(client, device)
    assert response.json()["error"]["code"] == "certificate_invalid"
    actions = db.scalars(text("SELECT action FROM audit_log")).all()
    assert {"certificate.issue", "certificate.revoke"} <= set(actions)
    crl = client.get(f"{URL}/crl", headers=admin).json()
    assert crl["revoked_serials"] == [cert["serial_number"]]
    again = client.post(
        revoke_url, json={"confirmation": confirmation()}, headers=admin
    )
    assert again.json()["error"]["code"] == "certificate_not_active"


def test_renew_replaces_certificate(
    client: TestClient, admin: dict[str, str], device: dict[str, Any], ca_dir: Path
) -> None:
    create_ca(ca_dir)
    old = issue(client, admin, device["node_id"])["certificate"]
    renewed = client.post(f"{URL}/{old['id']}/renew", json={"days": 30}, headers=admin)
    assert renewed.status_code == 201
    listing = client.get(URL, params={"status": "active"}, headers=admin).json()
    assert [c["id"] for c in listing["items"]] == [renewed.json()["certificate"]["id"]]
    assert heartbeat(client, device).status_code == 200


def test_expiry_report_and_timer(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    device: dict[str, Any],
    ca_dir: Path,
) -> None:
    create_ca(ca_dir)
    short = issue(client, admin, device["node_id"], days=10)["certificate"]
    issue(client, admin, device["node_id"], days=365)
    expiring = client.get(f"{URL}/expiring", params={"days": 30}, headers=admin)
    assert [c["id"] for c in expiring.json()] == [short["id"]]

    report = process_timers(db, datetime.now(UTC) + timedelta(days=11))
    assert report.expired_certificates == 1
    expired = client.get(URL, params={"status": "expired"}, headers=admin).json()
    assert expired["total"] == 1
    # Ще один чинний сертифікат: вузол проходить перевірку.
    assert heartbeat(client, device).status_code == 200


def test_unknown_node_is_404(
    client: TestClient, admin: dict[str, str], ca_dir: Path
) -> None:
    create_ca(ca_dir)
    response = client.post(
        URL, json={"node_id": "00000000-0000-0000-0000-000000000000"}, headers=admin
    )
    assert response.status_code == 404
