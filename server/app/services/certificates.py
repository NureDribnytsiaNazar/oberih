"""Власний центр сертифікації для IoT-вузлів (СЧ-9, критерій 3.6).

Кореневий ключ і сертифікат лежать у CA_DIR (поза репозиторієм) і
створюються скриптом scripts/init_ca.py. Приватний ключ вузла
повертається лише один раз під час випуску; у БД зберігаються тільки
сертифікат (PEM), серійний номер, строки дії та статус.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.errors import AppError, ConflictError, NotFoundError
from app.models.admin import Certificate
from app.models.devices import Node
from app.models.enums import CertificateStatus
from app.models.users import User
from app.pagination import PageParams, paginate
from app.services import audit

CA_KEY_FILE = "ca.key.pem"
CA_CERT_FILE = "ca.cert.pem"
ORGANIZATION = "Oberih"


@dataclass(frozen=True)
class IssuedCertificate:
    """Новий сертифікат і його приватний ключ (ключ показується один раз)."""

    certificate: Certificate
    private_key_pem: str


class CaNotInitializedError(AppError):
    """Кореневий сертифікат ще не створено (scripts/init_ca.py)."""

    def __init__(self) -> None:
        super().__init__(503, "ca_not_initialized")


# --- Центр сертифікації -------------------------------------------------------


def create_ca(ca_dir: Path, common_name: str = "Oberih Device CA") -> Path:
    """Створює самопідписаний кореневий сертифікат і ключ у ca_dir.

    Наявний центр сертифікації не перезаписується.
    """
    key_path, cert_path = ca_dir / CA_KEY_FILE, ca_dir / CA_CERT_FILE
    if key_path.exists() or cert_path.exists():
        raise FileExistsError(f"CA already exists in {ca_dir}")
    ca_dir.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = _name(common_name)
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(_key_pem(key))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path


def load_ca(ca_dir: Path) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    """Зчитує ключ і сертифікат центру сертифікації."""
    key_path, cert_path = ca_dir / CA_KEY_FILE, ca_dir / CA_CERT_FILE
    if not key_path.exists() or not cert_path.exists():
        raise CaNotInitializedError()
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise CaNotInitializedError()
    return key, x509.load_pem_x509_certificate(cert_path.read_bytes())


# --- Випуск, поновлення, відкликання -----------------------------------------


def issue(
    db: Session,
    ca_dir: Path,
    actor: User,
    node_id: uuid.UUID,
    days: int,
    subject: str | None = None,
) -> IssuedCertificate:
    """Випускає клієнтський сертифікат вузла, підписаний центром сертифікації."""
    node = db.get(Node, node_id)
    if node is None:
        raise NotFoundError()
    issued = _build(db, ca_dir, node, days, subject or f"node-{node.serial}")
    audit.record(
        db,
        actor.id,
        "certificate.issue",
        "certificate",
        issued.certificate.id,
        {"node_id": str(node.id), "serial": issued.certificate.serial_number},
    )
    db.commit()
    return issued


def renew(
    db: Session, ca_dir: Path, actor: User, certificate_id: uuid.UUID, days: int
) -> IssuedCertificate:
    """Випускає новий сертифікат замість старого; старий відкликається."""
    old = _get(db, certificate_id)
    if old.node_id is None:
        raise ConflictError("certificate_not_active")
    node = db.get_one(Node, old.node_id)
    issued = _build(db, ca_dir, node, days, old.subject)
    if old.status == CertificateStatus.ACTIVE:
        _revoke(old)
    audit.record(
        db,
        actor.id,
        "certificate.renew",
        "certificate",
        issued.certificate.id,
        {"replaces": str(old.id)},
    )
    db.commit()
    return issued


def revoke(db: Session, actor: User, certificate_id: uuid.UUID) -> Certificate:
    """Відкликає сертифікат; вузол із ним більше не проходить перевірку."""
    certificate = _get(db, certificate_id)
    if certificate.status != CertificateStatus.ACTIVE:
        raise ConflictError("certificate_not_active")
    _revoke(certificate)
    audit.record(db, actor.id, "certificate.revoke", "certificate", certificate.id)
    db.commit()
    return certificate


def mark_expired(db: Session, now: datetime) -> int:
    """Позначає прострочені активні сертифікати як expired (у таймерах)."""
    expired = db.scalars(
        select(Certificate).where(
            Certificate.status == CertificateStatus.ACTIVE,
            Certificate.not_after <= now,
        )
    ).all()
    for certificate in expired:
        certificate.status = CertificateStatus.EXPIRED
    return len(expired)


# --- Перегляд і перевірка ----------------------------------------------------


def list_certificates(
    db: Session,
    params: PageParams,
    status: CertificateStatus | None = None,
    node_id: uuid.UUID | None = None,
    expires_before: datetime | None = None,
) -> tuple[list[Certificate], int]:
    """Сертифікати з фільтрами за статусом, вузлом і строком дії."""
    stmt: Select[Certificate] = select(Certificate)
    if status is not None:
        stmt = stmt.where(Certificate.status == status)
    if node_id is not None:
        stmt = stmt.where(Certificate.node_id == node_id)
    if expires_before is not None:
        stmt = stmt.where(Certificate.not_after <= expires_before)
    return paginate(db, stmt.order_by(Certificate.not_after, Certificate.id), params)


def get_certificate(db: Session, certificate_id: uuid.UUID) -> Certificate:
    """Сертифікат за ідентифікатором."""
    return _get(db, certificate_id)


def expiring(db: Session, days: int, now: datetime) -> list[Certificate]:
    """Активні сертифікати, строк дії яких спливає протягом days днів."""
    return list(
        db.scalars(
            select(Certificate)
            .where(
                Certificate.status == CertificateStatus.ACTIVE,
                Certificate.not_after <= now + timedelta(days=days),
            )
            .order_by(Certificate.not_after)
        )
    )


def revoked_serials(db: Session) -> list[str]:
    """Перелік відкликаних серійних номерів (спрощений CRL)."""
    return list(
        db.scalars(
            select(Certificate.serial_number)
            .where(Certificate.status == CertificateStatus.REVOKED)
            .order_by(Certificate.serial_number)
        )
    )


def node_certificate_valid(db: Session, node_id: uuid.UUID, now: datetime) -> bool:
    """Перевірка під час автентифікації вузла.

    Вузол без сертифікатів проходить лише за токеном (перехідний період до
    mTLS у ЛБ5). Якщо сертифікати є, хоча б один має бути чинним: не
    відкликаним і в межах строку дії.
    """
    certificates = db.scalars(
        select(Certificate).where(Certificate.node_id == node_id)
    ).all()
    if not certificates:
        return True
    return any(
        cert.status == CertificateStatus.ACTIVE
        and cert.not_before <= now < cert.not_after
        for cert in certificates
    )


# --- Допоміжні функції -------------------------------------------------------


def _build(
    db: Session, ca_dir: Path, node: Node, days: int, subject: str
) -> IssuedCertificate:
    ca_key, ca_cert = load_ca(ca_dir)
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(UTC)
    serial = x509.random_serial_number()
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    certificate = Certificate(
        node_id=node.id,
        subject=subject,
        serial_number=format(serial, "x"),
        status=CertificateStatus.ACTIVE,
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        pem=cert.public_bytes(serialization.Encoding.PEM).decode(),
    )
    db.add(certificate)
    db.flush()
    return IssuedCertificate(certificate, _key_pem(key).decode())


def _revoke(certificate: Certificate) -> None:
    certificate.status = CertificateStatus.REVOKED
    certificate.revoked_at = datetime.now(UTC)


def _get(db: Session, certificate_id: uuid.UUID) -> Certificate:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise NotFoundError()
    return certificate


def _name(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _key_pem(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
