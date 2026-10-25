"""Автентифікація: реєстрація, вхід, токени, 2FA, формат помилок."""

import pyotp
from fastapi.testclient import TestClient

from tests.conftest import API, PASSWORD, login, register


def test_register_returns_profile_with_basic_tariff(client: TestClient) -> None:
    user = register(client, "Anna@Test.ua")
    assert user["email"] == "anna@test.ua"
    assert user["tariff_plan"]["code"] == "basic"
    assert user["privacy_consent_at"] is not None
    assert "password_hash" not in user


def test_register_requires_consent(client: TestClient) -> None:
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": "a@test.ua",
            "password": PASSWORD,
            "full_name": "A",
            "privacy_consent": False,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "consent_required"


def test_register_duplicate_email(client: TestClient) -> None:
    register(client, "a@test.ua")
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": "A@test.ua",
            "password": PASSWORD,
            "full_name": "A",
            "privacy_consent": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_validation_error_has_unified_format(client: TestClient) -> None:
    response = client.post(f"{API}/auth/register", json={"email": "bad"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]


def test_login_errors_are_localized(client: TestClient) -> None:
    register(client, "a@test.ua")
    body = {"email": "a@test.ua", "password": "wrong-password"}
    uk = client.post(f"{API}/auth/login", json=body)
    en = client.post(
        f"{API}/auth/login", json=body, headers={"Accept-Language": "en-US,en;q=0.9"}
    )
    assert uk.status_code == en.status_code == 401
    assert uk.json()["error"]["code"] == "invalid_credentials"
    assert uk.json()["error"]["message"].startswith("Неправильна")
    assert en.json()["error"]["message"] == "Invalid email or password"


def test_protected_endpoint_requires_token(client: TestClient) -> None:
    assert client.get(f"{API}/users/me").status_code == 401
    bad = {"Authorization": "Bearer not-a-jwt"}
    response = client.get(f"{API}/users/me", headers=bad)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_refresh_rotates_token_and_logout_revokes(client: TestClient) -> None:
    register(client, "a@test.ua")
    tokens = client.post(
        f"{API}/auth/login", json={"email": "a@test.ua", "password": PASSWORD}
    ).json()

    rotated = client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    # Старий токен оновлення після обміну більше не діє.
    reused = client.post(
        f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    new_refresh = rotated.json()["refresh_token"]
    logout = client.post(f"{API}/auth/logout", json={"refresh_token": new_refresh})
    assert logout.status_code == 204
    after = client.post(f"{API}/auth/refresh", json={"refresh_token": new_refresh})
    assert after.status_code == 401


def test_totp_two_factor_flow(client: TestClient) -> None:
    register(client, "a@test.ua")
    headers = login(client, "a@test.ua")
    setup = client.post(f"{API}/auth/totp/enable", headers=headers).json()
    totp = pyotp.TOTP(setup["secret"])

    wrong = client.post(
        f"{API}/auth/totp/verify", json={"code": "000000"}, headers=headers
    )
    if totp.now() != "000000":
        assert wrong.status_code == 401
    ok = client.post(
        f"{API}/auth/totp/verify", json={"code": totp.now()}, headers=headers
    )
    assert ok.status_code == 204

    no_code = client.post(
        f"{API}/auth/login", json={"email": "a@test.ua", "password": PASSWORD}
    )
    assert no_code.json()["error"]["code"] == "totp_required"
    login(client, "a@test.ua", totp_code=totp.now())
