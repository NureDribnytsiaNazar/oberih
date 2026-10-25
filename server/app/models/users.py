"""Користувачі, тарифні плани та службові токени."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import Locale, MeasurementSystem, PushPlatform


class TariffPlan(UUIDPrimaryKeyMixin, Base):
    """Тарифний план (таблиця 4 у Vision & Scope): обмеження та можливості."""

    __tablename__ = "tariff_plans"
    __table_args__ = (
        CheckConstraint("max_facilities > 0", name="max_facilities_positive"),
        CheckConstraint("archive_days > 0", name="archive_days_positive"),
    )

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    price_month: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    max_facilities: Mapped[int] = mapped_column(Integer)
    archive_days: Mapped[int] = mapped_column(Integer)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    guest_access: Mapped[bool] = mapped_column(Boolean, default=False)
    false_alarm_stats: Mapped[bool] = mapped_column(Boolean, default=False)
    incident_timeline: Mapped[bool] = mapped_column(Boolean, default=False)
    api_access: Mapped[bool] = mapped_column(Boolean, default=False)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Обліковий запис користувача системи."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(128))
    locale: Mapped[Locale] = mapped_column(enum_column(Locale), default=Locale.UK)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Kyiv")
    measurement_system: Mapped[MeasurementSystem] = mapped_column(
        enum_column(MeasurementSystem), default=MeasurementSystem.METRIC
    )
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tariff_plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tariff_plans.id", ondelete="RESTRICT")
    )
    privacy_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Заповнюється під час видалення даних (GDPR): запис знеособлюється,
    # а не видаляється, щоб не порушувати цілісність журналів.
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tariff_plan: Mapped[TariffPlan] = relationship()
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    push_tokens: Mapped[list["PushToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Токен оновлення доступу (зберігається лише хеш)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class PushToken(UUIDPrimaryKeyMixin, Base):
    """Токен пристрою користувача для push-повідомлень."""

    __tablename__ = "push_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(512), unique=True)
    platform: Mapped[PushPlatform] = mapped_column(enum_column(PushPlatform))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="push_tokens")
