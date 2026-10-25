"""Профіль, експорт і знеособлення облікового запису (GDPR)."""

from fastapi.testclient import TestClient

from tests.conftest import API, PASSWORD, create_facility, new_user


def test_update_profile(client: TestClient) -> None:
    headers = new_user(client, "a@test.ua")
    response = client.patch(
        f"{API}/users/me",
        json={"locale": "en", "timezone": "America/New_York"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["locale"] == "en"
    bad = client.patch(
        f"{API}/users/me", json={"timezone": "Mars/Olympus"}, headers=headers
    )
    assert bad.json()["error"]["code"] == "invalid_timezone"


def test_export_contains_personal_data(client: TestClient) -> None:
    headers = new_user(client, "a@test.ua")
    create_facility(client, headers)
    export = client.get(f"{API}/users/me/export", headers=headers).json()
    assert export["profile"]["email"] == "a@test.ua"
    assert export["memberships"][0]["role"] == "owner"
    assert "password_hash" not in export["profile"]


def test_delete_account_anonymizes_user(client: TestClient) -> None:
    headers = new_user(client, "a@test.ua")
    wrong = client.request(
        "DELETE", f"{API}/users/me", json={"password": "nope"}, headers=headers
    )
    assert wrong.status_code == 401

    response = client.request(
        "DELETE", f"{API}/users/me", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 204
    # Обліковий запис неактивний: ні токен, ні пароль більше не працюють.
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401
    relogin = client.post(
        f"{API}/auth/login", json={"email": "a@test.ua", "password": PASSWORD}
    )
    assert relogin.status_code == 401


def test_owner_must_delete_facilities_first(client: TestClient) -> None:
    headers = new_user(client, "a@test.ua")
    create_facility(client, headers)
    response = client.request(
        "DELETE", f"{API}/users/me", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "owns_facilities"
