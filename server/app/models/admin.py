"""Адміністрування: журнал аудиту, резервні копії та сертифікати."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import BackupKind, BackupStatus, CertificateStatus


class AuditLogEntry(Base):
    """Журнал доступу до даних і адміністративних дій (лише додавання)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        # Пошук записів аудиту щодо конкретної сутності (об'єкт, вузол тощо).
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Backup(UUIDPrimaryKeyMixin, Base):
    """Запис про резервну копію даних або налаштувань."""

    __tablename__ = "backups"

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    kind: Mapped[BackupKind] = mapped_column(enum_column(BackupKind))
    status: Mapped[BackupStatus] = mapped_column(
        enum_column(BackupStatus), default=BackupStatus.PENDING
    )
    file_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Certificate(UUIDPrimaryKeyMixin, Base):
    """Сертифікат пристрою або сервісу (керування сертифікатами)."""

    __tablename__ = "certificates"

    node_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255))
    serial_number: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[CertificateStatus] = mapped_column(
        enum_column(CertificateStatus), default=CertificateStatus.ACTIVE
    )
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    pem: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
