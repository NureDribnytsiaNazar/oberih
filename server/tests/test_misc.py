"""Сервісні ендпоінти, адміністрування, вибір мови."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.i18n import parse_accept_language
from app.models.enums import Locale
from tests.conftest import API, new_user


def test_health(client: TestClient) -> None:
    assert client.get(f"{API}/health").json() == {"status": "ok"}


def test_unknown_route_uses_error_format(client: TestClient) -> None:
    response = client.get(f"{API}/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_tariffs_are_public(client: TestClient) -> None:
    codes = [t["code"] for t in client.get(f"{API}/tariffs").json()]
    assert codes == ["basic", "standard", "professional"]


def test_admin_endpoints(client: TestClient, db: Session) -> None:
    user = new_user(client, "user@test.ua")
    assert client.get(f"{API}/admin/users", headers=user).status_code == 403

    admin = new_user(client, "admin@test.ua")
    db.execute(
        text("UPDATE users SET is_platform_admin = true WHERE email = :e"),
        {"e": "admin@test.ua"},
    )
    db.commit()
    users = client.get(f"{API}/admin/users", headers=admin).json()
    assert users["total"] == 2
    log = client.get(
        f"{API}/admin/audit-log",
        params={"action": "admin.users_view"},
        headers=admin,
    ).json()
    assert log["total"] == 1


def test_pagination_limits(client: TestClient) -> None:
    admin = new_user(client, "a@test.ua")
    response = client.get(f"{API}/facilities", params={"limit": 1000}, headers=admin)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, Locale.UK),
        ("en", Locale.EN),
        ("en-GB,en;q=0.9", Locale.EN),
        ("de-DE,en;q=0.5,uk;q=0.8", Locale.UK),
        ("fr", Locale.UK),
    ],
)
def test_accept_language(header: str | None, expected: Locale) -> None:
    assert parse_accept_language(header) == expected
