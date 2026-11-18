"""Скрипт демо-даних: створює все потрібне для показу й не дублює дані."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from scripts.seed import seed, seed_lab3


def test_seed_is_complete_and_idempotent(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ca_dir", tmp_path / "ca")
    assert seed(db, "demo-password-1") is not None
    assert seed_lab3(db) is True

    assert db.scalar(text("SELECT mode FROM facilities")) == "armed_away"
    assert db.scalar(text("SELECT count(*) FROM alarms WHERE is_false")) == 2
    statuses = db.scalars(text("SELECT status FROM certificates ORDER BY status"))
    assert list(statuses) == ["active", "revoked"]
    assert (tmp_path / "ca" / "ca.cert.pem").exists()

    assert seed(db, "demo-password-1") is None
    assert seed_lab3(db) is False
    assert db.scalar(text("SELECT count(*) FROM test_scenarios")) == 1
