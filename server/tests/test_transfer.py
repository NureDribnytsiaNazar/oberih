"""Експорт та імпорт налаштувань, експорт подій у CSV."""

import csv
import io
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.conftest import API, create_facility, set_tariff


def export(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> dict[str, Any]:
    response = client.get(f"{API}/facilities/{facility_id}/export", headers=owner)
    assert response.status_code == 200, response.text
    return dict(response.json())


def import_doc(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    doc: dict[str, Any],
    dry_run: bool = False,
) -> Any:
    return client.post(
        f"{API}/facilities/{facility_id}/import",
        params={"dry_run": str(dry_run).lower()},
        json=doc,
        headers=owner,
    )


def add_scenario(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    sensor = db.scalar(text("SELECT id FROM sensors WHERE channel = 1"))
    client.post(
        f"{API}/facilities/{facility_id}/scenarios",
        json={
            "name": "Двері",
            "steps": [{"offset_ms": 0, "sensor_id": str(sensor), "state": "opened"}],
            "expected": [{"level": "alarm"}],
        },
        headers=owner,
    )


def test_export_contains_settings_with_natural_keys(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    add_scenario(client, db, owner, facility_id)
    doc = export(client, owner, facility_id)
    assert doc["format_version"] == 1
    assert len(doc["zones"]) == 3
    [node] = doc["nodes"]
    assert node["serial"] == "ESP32-0001"
    assert [s["channel"] for s in node["sensors"]] == [1, 2, 3]
    assert "device_token_hash" not in node
    assert doc["scenarios"][0]["steps"][0] == {
        "offset_ms": 0,
        "node_serial": "ESP32-0001",
        "channel": 1,
        "state": "opened",
    }


def test_reimport_is_idempotent(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    add_scenario(client, db, owner, facility_id)
    doc = export(client, owner, facility_id)
    report = import_doc(client, owner, facility_id, doc).json()
    assert sum(report["created"].values()) == 0
    assert sum(report["updated"].values()) == 0
    assert report["unchanged"]["sensors"] == 3


def test_dry_run_writes_nothing_then_import_creates(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    set_tariff(db, "owner@test.ua", "standard")
    target = create_facility(client, owner)
    doc = export(client, owner, facility_id)
    doc["nodes"] = []  # вузол не можна перенести: серійний номер уже зайнятий
    doc["settings"]["entry_delay_s"] = 45

    preview = import_doc(client, owner, target, doc, dry_run=True).json()
    assert preview["dry_run"] is True
    assert preview["created"]["zones"] == 3
    assert preview["updated"]["settings"] == 1
    count = text("SELECT count(*) FROM zones WHERE facility_id = :f")
    assert db.scalar(count, {"f": target}) == 0

    applied = import_doc(client, owner, target, doc).json()
    assert applied["created"] == preview["created"]
    assert db.scalar(count, {"f": target}) == 3
    settings = client.get(f"{API}/facilities/{target}/settings", headers=owner).json()
    assert settings["entry_delay_s"] == 45


def test_import_errors_point_to_field(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    set_tariff(db, "owner@test.ua", "standard")
    target = create_facility(client, owner)
    doc = export(client, owner, facility_id)

    taken = import_doc(client, owner, target, doc).json()["error"]
    assert taken["code"] == "import_invalid"
    assert taken["details"][0]["loc"] == ["nodes", 0, "serial"]

    doc["nodes"] = []
    doc["zones"][0]["zone_type"] = "garden"
    invalid = import_doc(client, owner, target, doc)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"][0]["loc"] == [
        "body",
        "zones",
        0,
        "zone_type",
    ]
    count = text("SELECT count(*) FROM zones WHERE facility_id = :f")
    assert db.scalar(count, {"f": target}) == 0


def insert_event(
    db: Session, device: dict[str, Any], facility_id: str, moment: datetime, seq: int
) -> None:
    db.execute(
        text(
            "INSERT INTO events (facility_id, node_id, sensor_id, event_type, seq,"
            " occurred_at) SELECT :f, :n, id, 'opened', :s, :t FROM sensors"
            " WHERE channel = 1"
        ),
        {"f": facility_id, "n": device["node_id"], "s": seq, "t": moment},
    )
    db.commit()


def read_csv(content: bytes, delimiter: str) -> list[list[str]]:
    assert content.startswith("﻿".encode())
    rows = csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter=delimiter)
    return list(rows)


def test_events_csv_follows_locale_and_dst(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    device: dict[str, Any],
) -> None:
    # 29.03.2026 о 03:00 за Києвом годинник переводять на літній час.
    insert_event(db, device, facility_id, datetime(2026, 3, 29, 0, 30, tzinfo=UTC), 1)
    insert_event(db, device, facility_id, datetime(2026, 3, 29, 1, 30, tzinfo=UTC), 2)
    url = f"{API}/facilities/{facility_id}/events/export"

    uk = client.get(url, params={"tz": "Europe/Kyiv"}, headers=owner)
    assert uk.headers["content-type"].startswith("text/csv")
    header, first, second = read_csv(uk.content, ";")
    assert header[0] == "Номер"
    assert first[3] == "Відчинено"
    assert first[2].endswith("02:30:00")  # UTC+2
    assert second[2].endswith("04:30:00")  # UTC+3 після переходу
    assert first[4] == "Вхідні двері"

    en = client.get(url, params={"tz": "Europe/Kyiv", "locale": "en"}, headers=owner)
    header, first, _ = read_csv(en.content, ",")
    assert header[0] == "Number"
    assert first[3] == "Opened"
    assert first[2].startswith("Mar 29, 2026")
