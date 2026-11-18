"""Адміністрування: користувачі, статистика, очищення даних, аудит."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import API, PASSWORD, confirmation, login, new_user


def make_admin(db: Session, email: str) -> None:
    db.execute(
        text("UPDATE users SET is_platform_admin = true WHERE email = :e"), {"e": email}
    )
    db.commit()


@pytest.fixture()
def admin(client: TestClient, db: Session) -> dict[str, str]:
    headers = new_user(client, "admin@test.ua")
    make_admin(db, "admin@test.ua")
    return headers


def user_id(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.get(f"{API}/users/me", headers=headers).json()["id"])


def audit_actions(db: Session) -> list[str]:
    return list(db.scalars(text("SELECT action FROM audit_log ORDER BY id")).all())


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/admin/stats"),
        ("get", "/admin/backups"),
        ("get", "/admin/certificates"),
        ("post", "/admin/data/purge"),
        ("post", "/admin/users/00000000-0000-0000-0000-000000000000/block"),
    ],
)
def test_admin_endpoints_require_platform_admin(
    client: TestClient, method: str, path: str
) -> None:
    user = new_user(client, "user@test.ua")
    response = client.request(method, f"{API}{path}", headers=user, json={})
    assert response.status_code == 403


def test_block_and_unblock_user(
    client: TestClient, db: Session, admin: dict[str, str]
) -> None:
    user = new_user(client, "user@test.ua")
    uid = user_id(client, user)
    blocked = client.post(f"{API}/admin/users/{uid}/block", headers=admin)
    assert blocked.json()["blocked_at"] is not None

    # Чинний токен доступу й новий вхід відхиляються.
    assert client.get(f"{API}/users/me", headers=user).json()["error"]["code"] == (
        "account_blocked"
    )
    response = client.post(
        f"{API}/auth/login", json={"email": "user@test.ua", "password": PASSWORD}
    )
    assert response.json()["error"]["code"] == "account_blocked"
    active = db.scalar(
        text("SELECT count(*) FROM refresh_tokens WHERE revoked_at IS NULL")
    )
    assert active == 1  # лише сесія адміністратора

    client.post(f"{API}/admin/users/{uid}/unblock", headers=admin)
    login(client, "user@test.ua")
    assert {"admin.user_block", "admin.user_unblock"} <= set(audit_actions(db))


def test_admin_cannot_block_self(client: TestClient, admin: dict[str, str]) -> None:
    uid = user_id(client, admin)
    response = client.post(f"{API}/admin/users/{uid}/block", headers=admin)
    assert response.json()["error"]["code"] == "cannot_block_self"


def test_last_admin_cannot_lose_rights(
    client: TestClient, db: Session, admin: dict[str, str]
) -> None:
    uid = user_id(client, admin)
    url = f"{API}/admin/users/{uid}/platform-admin"
    response = client.put(url, json={"is_platform_admin": False}, headers=admin)
    assert response.json()["error"]["code"] == "last_admin"

    second = new_user(client, "second@test.ua")
    second_id = user_id(client, second)
    granted = client.put(
        f"{API}/admin/users/{second_id}/platform-admin",
        json={"is_platform_admin": True},
        headers=admin,
    )
    assert granted.json()["is_platform_admin"] is True
    revoked = client.put(url, json={"is_platform_admin": False}, headers=second)
    assert revoked.json()["is_platform_admin"] is False


def test_sessions_totp_and_tariff(
    client: TestClient, db: Session, admin: dict[str, str]
) -> None:
    user = new_user(client, "user@test.ua")
    uid = user_id(client, user)
    revoked = client.post(f"{API}/admin/users/{uid}/sessions/revoke", headers=admin)
    assert revoked.json() == {"revoked": 1}

    client.post(f"{API}/auth/totp/enable", headers=user)
    reset = client.post(f"{API}/admin/users/{uid}/totp/reset", headers=admin)
    assert reset.json()["totp_enabled"] is False

    tariff_url = f"{API}/admin/users/{uid}/tariff"
    changed = client.put(tariff_url, json={"code": "professional"}, headers=admin)
    assert changed.json()["tariff_plan"]["code"] == "professional"
    unknown = client.put(tariff_url, json={"code": "gold"}, headers=admin)
    assert unknown.json()["error"]["code"] == "unknown_tariff"


def test_anonymized_user_is_not_editable(
    client: TestClient, admin: dict[str, str]
) -> None:
    user = new_user(client, "user@test.ua")
    uid = user_id(client, user)
    client.request(
        "DELETE", f"{API}/users/me", json={"password": PASSWORD}, headers=user
    )
    response = client.post(f"{API}/admin/users/{uid}/block", headers=admin)
    assert response.json()["error"]["code"] == "user_anonymized"


def test_system_stats(
    client: TestClient, admin: dict[str, str], owner: dict[str, str], facility_id: str
) -> None:
    stats = client.get(f"{API}/admin/stats", headers=admin).json()
    assert (stats["users"], stats["facilities"]) == (2, 1)
    assert stats["archive_bytes"] > 0


def test_purge_removes_only_expired_data(
    client: TestClient,
    db: Session,
    admin: dict[str, str],
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    client.post(
        f"{API}/facilities/{facility_id}/arm", json={"mode": "home"}, headers=owner
    )
    now = datetime.now(UTC)
    for seq, age in ((1, timedelta(days=8)), (2, timedelta(days=1))):
        db.execute(
            text(
                "INSERT INTO events"
                " (facility_id, node_id, event_type, seq, occurred_at)"
                " VALUES (:f, :n, 'closed', :s, :t)"
            ),
            {"f": facility_id, "n": device["node_id"], "s": seq, "t": now - age},
        )
    db.commit()

    url = f"{API}/admin/data/purge"
    assert client.post(url, json={}, headers=admin).status_code == 401
    result = client.post(url, json={"confirmation": confirmation()}, headers=admin)
    # Тариф basic зберігає події 7 днів.
    assert result.json() == {"alarms": 0, "events": 1}
    assert db.scalar(text("SELECT count(*) FROM events")) == 1
    assert db.scalar(text("SELECT count(*) FROM arming_log")) == 1
    assert "data.purge" in audit_actions(db)
