"""Скрипт демо-даних: створює все потрібне для показу й не дублює дані."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from cryptography import x509

from scripts.make_dev_cert import make_certificate
from scripts.provision_node import provision, render_secrets, resolve_ca
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


def test_provision_node_rotates_secrets(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "ca_dir", tmp_path / "ca")
    credentials = seed(db, "demo-password-1")
    assert credentials is not None and len(credentials.command_key) == 64

    node, token, key = provision(db, "ESP32-DEMO-001")
    assert token != credentials.device_token
    assert key.hex() != credentials.command_key
    content = render_secrets(node, token, key, "https://demo.example")
    assert f'#define OBERIH_COMMAND_KEY "{key.hex()}"' in content
    assert '#define OBERIH_SERVER_URL "https://demo.example"' in content
    assert "OBERIH_CA_CERT" not in content

    pem = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"
    with_ca = render_secrets(node, token, key, "https://demo.example", pem)
    assert (
        '#define OBERIH_CA_CERT \\\n  "-----BEGIN CERTIFICATE-----\\n" \\\n' in with_ca
    )
    assert '  "-----END CERTIFICATE-----\\n"\n' in with_ca


def test_dev_certificate_and_ca_file(tmp_path: Path) -> None:
    cert_pem, key_pem = make_certificate(["bore.pub", "localhost"])
    certificate = x509.load_pem_x509_certificate(cert_pem)
    names = certificate.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.DNSName)
    assert names == ["bore.pub", "localhost"]
    assert b"PRIVATE KEY" in key_pem

    ca_file = tmp_path / "server.crt"
    ca_file.write_bytes(cert_pem)
    assert resolve_ca("https://bore.pub:1234", "issuer", ca_file, False) == (
        cert_pem.decode()
    )
    assert resolve_ca("https://bore.pub:1234", "issuer", ca_file, True) is None
