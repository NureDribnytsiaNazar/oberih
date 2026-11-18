"""Інтернаціоналізація: місцевий час, формати, одиниці, сортування, мови."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.l10n import format_local, to_local
from app.models.enums import Locale, MeasurementSystem, TimeFormat
from app.units import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    feet_to_metres,
    length,
    metres_to_feet,
    temperature,
)
from tests.conftest import API

BEFORE_DST = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)  # 02:30 за Києвом (UTC+2)
AFTER_DST = datetime(2026, 3, 29, 1, 30, tzinfo=UTC)  # 04:30 за Києвом (UTC+3)


def test_units_conversion() -> None:
    assert celsius_to_fahrenheit(Decimal("100")) == Decimal("212")
    assert fahrenheit_to_celsius(Decimal("32")) == Decimal("0")
    assert feet_to_metres(metres_to_feet(Decimal("2"))) == Decimal("2")
    assert length(Decimal("10"), MeasurementSystem.IMPERIAL).unit == "ft"
    assert temperature(Decimal("21.5"), MeasurementSystem.METRIC).value == Decimal(
        "21.5"
    )
    assert temperature(Decimal("20"), MeasurementSystem.IMPERIAL).value == Decimal(
        "68.0"
    )


def test_local_time_across_dst_change() -> None:
    assert to_local(BEFORE_DST, "Europe/Kyiv").utcoffset() == timedelta(hours=2)
    assert to_local(AFTER_DST, "Europe/Kyiv").utcoffset() == timedelta(hours=3)
    text_uk = format_local(BEFORE_DST, "Europe/Kyiv", Locale.UK, TimeFormat.H24)
    assert text_uk == "29.03.2026 02:30:00"
    text_en = format_local(AFTER_DST, "Europe/Kyiv", Locale.EN, TimeFormat.H12)
    assert text_en == "03/29/2026 4:30:00 AM"


def test_events_include_local_time_and_units(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    db.execute(
        text(
            "INSERT INTO events"
            " (facility_id, node_id, event_type, occurred_at, payload)"
            " VALUES (:f, :n, 'node_online', :t, '{\"temperature_c\": 20}')"
        ),
        {"f": facility_id, "n": device["node_id"], "t": BEFORE_DST},
    )
    db.commit()
    client.patch(
        f"{API}/users/me",
        json={"measurement_system": "imperial", "time_format": "12h", "locale": "en"},
        headers=owner,
    )
    url = f"{API}/facilities/{facility_id}/events"
    event = client.get(url, params={"tz": "Europe/Kyiv"}, headers=owner).json()[
        "items"
    ][0]
    assert event["occurred_at"].startswith("2026-03-29T00:30:00")
    assert event["time_local"].startswith("2026-03-29T02:30:00+02:00")
    assert event["time_local_text"].startswith("03/29/2026 2:30:00")
    assert event["measurements"] == [
        {"name": "temperature", "value": "68.0", "unit": "°F"}
    ]
    bad = client.get(url, params={"tz": "Mars/Base"}, headers=owner)
    assert bad.json()["error"]["code"] == "invalid_timezone"


def test_zones_sorted_by_ukrainian_alphabet(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> None:
    url = f"{API}/facilities/{facility_id}/zones"
    for name in ("Ірпінь", "Житло", "Євро"):
        client.post(url, json={"name": name, "zone_type": "perimeter"}, headers=owner)
    names = [zone["name"] for zone in client.get(url, headers=owner).json()]
    assert names == ["Євро", "Житло", "Ірпінь"]


def test_locales_report_text_direction(client: TestClient) -> None:
    locales = {item["code"]: item for item in client.get(f"{API}/locales").json()}
    assert locales["uk"]["direction"] == "ltr" and locales["uk"]["supported"]
    assert locales["ar"]["direction"] == "rtl" and not locales["ar"]["supported"]


@pytest.mark.parametrize(("language", "word"), [("uk", "Отримати"), ("en", "Get")])
def test_privacy_statement_is_localized(
    client: TestClient, language: str, word: str
) -> None:
    body = client.get(f"{API}/privacy", headers={"Accept-Language": language}).json()
    assert body["locale"] == language
    assert body["rights"][0]["description"].startswith(word)
    assert {item["tariff"] for item in body["retention_by_tariff"]} == {
        "basic",
        "standard",
        "professional",
    }


def test_profile_language_used_without_header(
    client: TestClient, owner: dict[str, str]
) -> None:
    client.patch(f"{API}/users/me", json={"locale": "en"}, headers=owner)
    response = client.get(
        f"{API}/facilities/{'0' * 8}-0000-0000-0000-{'0' * 12}", headers=owner
    )
    assert response.json()["error"]["message"] == "Resource not found"
    explicit = client.get(
        f"{API}/facilities/{'0' * 8}-0000-0000-0000-{'0' * 12}",
        headers={**owner, "Accept-Language": "uk"},
    )
    assert explicit.json()["error"]["message"] == "Ресурс не знайдено"
