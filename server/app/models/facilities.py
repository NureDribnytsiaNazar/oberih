"""Об'єкти охорони, зони, налаштування, учасники, розклади та сповіщення."""

import uuid
from datetime import datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import (
    AlarmLevel,
    FacilityMode,
    FacilityRole,
    NotificationChannel,
    ScheduleAction,
    ZoneType,
)
from app.models.users import User


class Facility(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Об'єкт охорони (житло)."""

    __tablename__ = "facilities"

    name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Kyiv")
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    mode: Mapped[FacilityMode] = mapped_column(
        enum_column(FacilityMode), default=FacilityMode.DISARMED
    )
    mode_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    settings: Mapped["FacilitySettings"] = relationship(
        back_populates="facility", cascade="all, delete-orphan", uselist=False
    )
    zones: Mapped[list["Zone"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    members: Mapped[list["FacilityMember"]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )


class FacilitySettings(Base):
    """Параметри бізнес-логіки об'єкта (значення за замовчуванням з розділу 2.2.2)."""

    __tablename__ = "facility_settings"
    __table_args__ = (
        CheckConstraint("exit_delay_s >= 0", name="exit_delay_non_negative"),
        CheckConstraint("entry_delay_s >= 0", name="entry_delay_non_negative"),
        CheckConstraint("duplicate_window_s > 0", name="duplicate_window_positive"),
        CheckConstraint("confirm_window_s > 0", name="confirm_window_positive"),
        CheckConstraint("poll_interval_s > 0", name="poll_interval_positive"),
        CheckConstraint("missed_polls_limit > 0", name="missed_polls_positive"),
        CheckConstraint(
            "alarm_threshold <= confirmed_threshold", name="thresholds_ordered"
        ),
        CheckConstraint(
            "far_threshold >= 0 AND far_threshold <= 1", name="far_threshold_range"
        ),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), primary_key=True
    )
    exit_delay_s: Mapped[int] = mapped_column(Integer, default=30)
    entry_delay_s: Mapped[int] = mapped_column(Integer, default=30)
    duplicate_window_s: Mapped[int] = mapped_column(Integer, default=5)
    confirm_window_s: Mapped[int] = mapped_column(Integer, default=60)
    poll_interval_s: Mapped[int] = mapped_column(Integer, default=30)
    missed_polls_limit: Mapped[int] = mapped_column(Integer, default=3)
    weight_reed: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.5"))
    weight_pir: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.4"))
    weight_tamper: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("1.0")
    )
    alarm_threshold: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.4")
    )
    confirmed_threshold: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.9")
    )
    far_window_days: Mapped[int] = mapped_column(Integer, default=30)
    far_min_alarms: Mapped[int] = mapped_column(Integer, default=5)
    far_threshold: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), default=Decimal("0.3")
    )

    facility: Mapped[Facility] = relationship(back_populates="settings")


class FacilityMember(UUIDPrimaryKeyMixin, Base):
    """Користувач на об'єкті з певною роллю; гостьовий доступ обмежується часом."""

    __tablename__ = "facility_members"
    __table_args__ = (
        UniqueConstraint("facility_id", "user_id", name="uq_facility_members_pair"),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[FacilityRole] = mapped_column(enum_column(FacilityRole))
    access_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    facility: Mapped[Facility] = relationship(back_populates="members")
    user: Mapped[User] = relationship()


class Zone(UUIDPrimaryKeyMixin, Base):
    """Зона об'єкта: периметральна, внутрішня або цілодобова."""

    __tablename__ = "zones"
    __table_args__ = (
        UniqueConstraint("facility_id", "name", name="uq_zones_facility_name"),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    zone_type: Mapped[ZoneType] = mapped_column(enum_column(ZoneType))

    facility: Mapped[Facility] = relationship(back_populates="zones")


class Schedule(UUIDPrimaryKeyMixin, Base):
    """Розклад автоматичної постановки/зняття (місцевий час об'єкта)."""

    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint("days_mask BETWEEN 1 AND 127", name="days_mask_range"),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    action: Mapped[ScheduleAction] = mapped_column(enum_column(ScheduleAction))
    # Бітова маска днів тижня: біт 0 — понеділок, біт 6 — неділя.
    days_mask: Mapped[int] = mapped_column(SmallInteger)
    local_time: Mapped[time] = mapped_column(Time)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Момент (UTC), для якого розклад востаннє спрацював: не дає виконати
    # той самий запуск двічі.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationSetting(UUIDPrimaryKeyMixin, Base):
    """Налаштування сповіщень користувача для об'єкта."""

    __tablename__ = "notification_settings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "facility_id", "channel", name="uq_notification_settings_key"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        enum_column(NotificationChannel)
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_level: Mapped[AlarmLevel] = mapped_column(
        enum_column(AlarmLevel, name="notification_min_level"),
        default=AlarmLevel.ALARM,
    )
