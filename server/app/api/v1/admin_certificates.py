"""Маршрути керування сертифікатами вузлів (власний центр сертифікації)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from app.config import settings
from app.deps import AdminUser, DbSession, Paging
from app.models.enums import CertificateStatus
from app.pagination import page_response
from app.schemas.admin import (
    CertificateIssue,
    CertificateIssued,
    CertificateOut,
    CertificateRenew,
    ConfirmedAction,
    CrlOut,
)
from app.schemas.common import Page
from app.services import certificates as service
from app.services.certificates import IssuedCertificate
from app.services.reauth import confirm_action

router = APIRouter(prefix="/admin/certificates", tags=["certificates"])


def _issued(issued: IssuedCertificate) -> CertificateIssued:
    return CertificateIssued(
        certificate=CertificateOut.model_validate(issued.certificate),
        private_key_pem=issued.private_key_pem,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def issue_certificate(
    data: CertificateIssue, admin: AdminUser, db: DbSession
) -> CertificateIssued:
    """Випуск сертифіката вузла; приватний ключ повертається один раз."""
    issued = service.issue(
        db, settings.ca_dir, admin, data.node_id, data.days, data.subject
    )
    return _issued(issued)


@router.get("", response_model=Page[CertificateOut])
def list_certificates(
    admin: AdminUser,
    db: DbSession,
    paging: Paging,
    status_filter: Annotated[CertificateStatus | None, Query(alias="status")] = None,
    node_id: uuid.UUID | None = None,
    expires_before: AwareDatetime | None = None,
) -> object:
    """Сертифікати з фільтрами за статусом, вузлом і строком дії."""
    page = service.list_certificates(db, paging, status_filter, node_id, expires_before)
    return page_response(page, paging)


@router.get("/crl")
def revocation_list(admin: AdminUser, db: DbSession) -> CrlOut:
    """Перелік відкликаних серійних номерів."""
    return CrlOut(
        generated_at=datetime.now(UTC), revoked_serials=service.revoked_serials(db)
    )


@router.get("/expiring", response_model=list[CertificateOut])
def expiring_certificates(
    admin: AdminUser,
    db: DbSession,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> object:
    """Активні сертифікати, строк дії яких спливає протягом days днів."""
    return service.expiring(db, days, datetime.now(UTC))


@router.get("/{certificate_id}", response_model=CertificateOut)
def get_certificate(
    certificate_id: uuid.UUID, admin: AdminUser, db: DbSession
) -> object:
    """Сертифікат за ідентифікатором."""
    return service.get_certificate(db, certificate_id)


@router.post("/{certificate_id}/revoke", response_model=CertificateOut)
def revoke_certificate(
    certificate_id: uuid.UUID, data: ConfirmedAction, admin: AdminUser, db: DbSession
) -> object:
    """Відкликання (потрібне підтвердження); вузол перестає проходити перевірку."""
    confirm_action(admin, data.confirmation)
    return service.revoke(db, admin, certificate_id)


@router.post("/{certificate_id}/renew", status_code=status.HTTP_201_CREATED)
def renew_certificate(
    certificate_id: uuid.UUID, data: CertificateRenew, admin: AdminUser, db: DbSession
) -> CertificateIssued:
    """Поновлення: новий сертифікат замість старого, старий відкликається."""
    issued = service.renew(db, settings.ca_dir, admin, certificate_id, data.days)
    return _issued(issued)
