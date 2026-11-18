"""Резервні копії: створення, відновлення, пошкоджені файли, атомарність."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from tests.conftest import API, confirmation
from tests.test_admin import make_admin


@pytest.fixture(autouse=True)
def backup_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "backup_dir", tmp_path / "backups")
    return settings.backup_dir


@pytest.fixture()
def admin(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> dict[str, str]:
    """Адміністратор — власник об'єкта, щоб він був і в копії."""
    make_admin(db, "owner@test.ua")
    return owner


def create(
    client: TestClient, admin: dict[str, str], kind: str = "full"
) -> dict[str, Any]:
    response = client.post(f"{API}/admin/backups", json={"kind": kind}, headers=admin)
    assert response.status_code == 201, response.text
    return dict(response.json())


def restore(client: TestClient, admin: dict[str, str], backup_id: str) -> Any:
    return client.post(
        f"{API}/admin/backups/{backup_id}/restore",
        json={"confirmation": confirmation()},
        headers=admin,
    )


def zone_names(db: Session) -> list[str]:
    """Назви зон; транзакція одразу завершується, щоб не блокувати TRUNCATE."""
    names = list(db.scalars(text("SELECT name FROM zones ORDER BY name")).all())
    db.commit()
    return names


def test_full_backup_restore_roundtrip(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
    backup_dir: Path,
) -> None:
    backup = create(client, admin)
    assert backup["status"] == "completed"
    assert (backup_dir / backup["file_name"]).exists()
    before = zone_names(db)

    base = f"{API}/facilities/{facility_id}"
    client.post(
        f"{base}/zones", json={"name": "Гараж", "zone_type": "perimeter"}, headers=admin
    )
    client.patch(base, json={"name": "Змінено"}, headers=admin)
    assert "Гараж" in zone_names(db)

    response = restore(client, admin, backup["id"])
    assert response.status_code == 200, response.text
    db.expire_all()
    assert zone_names(db) == before
    name = db.scalar(text("SELECT name FROM facilities"))
    assert name == "Квартира"
    # Вузол після відновлення автентифікується тим самим токеном (хеш у копії).
    beat = client.post(f"{API}/device/heartbeat", json={}, headers=device["headers"])
    assert beat.status_code == 200
    actions = db.scalars(text("SELECT action FROM audit_log")).all()
    assert "backup.restore" in actions


def test_restore_requires_confirmation(
    client: TestClient, admin: dict[str, str]
) -> None:
    backup = create(client, admin)
    url = f"{API}/admin/backups/{backup['id']}/restore"
    response = client.post(url, json={}, headers=admin)
    assert response.json()["error"]["code"] == "reauth_required"


def test_corrupted_file_is_rejected(
    client: TestClient, admin: dict[str, str], backup_dir: Path
) -> None:
    backup = create(client, admin)
    path = backup_dir / backup["file_name"]
    path.write_bytes(path.read_bytes() + b"tampered")
    response = restore(client, admin, backup["id"])
    assert response.json()["error"]["code"] == "backup_corrupted"


def test_failure_mid_restore_leaves_no_partial_data(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    facility_id: str,
    backup_dir: Path,
) -> None:
    client.post(
        f"{API}/facilities/{facility_id}/zones",
        json={"name": "Двері", "zone_type": "perimeter"},
        headers=admin,
    )
    backup = create(client, admin)
    path = backup_dir / backup["file_name"]
    payload = json.loads(gzip.decompress(path.read_bytes()))
    # Зона посилається на неіснуючий об'єкт: вставка впаде посеред відновлення.
    payload["tables"]["zones"][0][
        "facility_id"
    ] = "00000000-0000-0000-0000-000000000000"
    data = gzip.compress(json.dumps(payload).encode())
    path.write_bytes(data)
    db.execute(
        text("UPDATE backups SET sha256 = :h WHERE id = :id"),
        {"h": hashlib.sha256(data).hexdigest(), "id": backup["id"]},
    )
    db.commit()

    client.post(
        f"{API}/facilities/{facility_id}/zones",
        json={"name": "Вікно", "zone_type": "perimeter"},
        headers=admin,
    )
    response = restore(client, admin, backup["id"])
    assert response.json()["error"]["code"] == "backup_restore_failed"
    db.expire_all()
    # Дані залишилися такими, як до спроби відновлення.
    assert zone_names(db) == ["Вікно", "Двері"]


def test_settings_backup_has_no_device_tokens_and_is_idempotent(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    device: dict[str, Any],
    backup_dir: Path,
) -> None:
    backup = create(client, admin, kind="settings")
    payload = json.loads(
        gzip.decompress((backup_dir / backup["file_name"]).read_bytes())
    )
    assert "users" not in payload["tables"]
    assert all("device_token_hash" not in node for node in payload["tables"]["nodes"])

    for _ in range(2):
        assert restore(client, admin, backup["id"]).status_code == 200
    assert db.scalar(text("SELECT count(*) FROM zones")) == 3
    beat = client.post(f"{API}/device/heartbeat", json={}, headers=device["headers"])
    assert beat.status_code == 200


def test_download_and_delete(
    client: TestClient, db: Session, admin: dict[str, str], backup_dir: Path
) -> None:
    backup = create(client, admin)
    download = client.get(f"{API}/admin/backups/{backup['id']}/download", headers=admin)
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == backup["sha256"]

    url = f"{API}/admin/backups/{backup['id']}"
    assert client.request("DELETE", url, json={}, headers=admin).status_code == 401
    deleted = client.request(
        "DELETE", url, json={"confirmation": confirmation()}, headers=admin
    )
    assert deleted.status_code == 204
    assert not (backup_dir / backup["file_name"]).exists()
    actions = db.scalars(text("SELECT action FROM audit_log")).all()
    assert "backup.delete" in actions
