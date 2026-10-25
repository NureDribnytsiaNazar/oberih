"""Незмінність журналів (тригери БД) і каскадне видалення об'єкта."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.conftest import API, new_user


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE arming_log SET to_mode = 'disarmed'",
        "DELETE FROM arming_log",
        "UPDATE audit_log SET action = 'forged'",
        "DELETE FROM audit_log",
    ],
)
def test_logs_are_append_only(
    client: TestClient,
    db: Session,
    owner: dict[str, str],
    facility_id: str,
    statement: str,
) -> None:
    client.post(
        f"{API}/facilities/{facility_id}/arm", json={"mode": "home"}, headers=owner
    )
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(statement))
    db.rollback()


def test_facility_delete_cascades_through_log(
    client: TestClient, db: Session, owner: dict[str, str], facility_id: str
) -> None:
    base = f"{API}/facilities/{facility_id}"
    client.post(f"{base}/arm", json={"mode": "home"}, headers=owner)
    client.post(
        f"{base}/zones", json={"name": "Двері", "zone_type": "perimeter"}, headers=owner
    )

    stranger = new_user(client, "stranger@test.ua")
    assert client.delete(base, headers=stranger).status_code == 404
    assert client.delete(base, headers=owner).status_code == 204

    remaining = db.scalar(text("SELECT count(*) FROM arming_log"))
    assert remaining == 0
    # Запис про видалення лишається в журналі аудиту.
    actions = db.scalars(text("SELECT action FROM audit_log")).all()
    assert "facility.delete" in actions
