"""Події, тривоги, журнали дій, хронології інцидентів та тестові сценарії."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import (
    AckAction,
    ActionSource,
    AlarmLevel,
    AlarmStatus,
    AuthMethod,
    EventType,
    FacilityMode,
)


class Event(Base):
    """Подія від датчика або вузла (архів подій).

    Унікальність (вузол, датчик, тип, порядковий номер) забезпечує
    ідемпотентність: повторне надсилання буфера не створює дублікатів.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "node_id",
            "sensor_id",
            "event_type",
            "seq",
            name="uq_events_dedup_key",
        ),
        # Пошук попередніх подій датчика у вікні Δ(дубл.) і Δ(підтв.).
        Index("ix_events_dedup_window", "sensor_id", "event_type", "occurred_at"),
        Index("ix_events_facility_occurred", "facility_id", "occurred_at"),
        Index("ix_events_sensor_occurred", "sensor_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE")
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE")
    )
    sensor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL")
    )
    event_type: Mapped[EventType] = mapped_column(enum_column(EventType))
    seq: Mapped[int | None] = mapped_column(BigInteger)
    # Час події на пристрої та час отримання сервером (обидва в UTC).
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Alarm(UUIDPrimaryKeyMixin, Base):
    """Тривога, створена за результатами обробки подій."""

    __tablename__ = "alarms"
    __table_args__ = (
        CheckConstraint("confidence >= 0", name="confidence_non_negative"),
        Index("ix_alarms_facility_opened", "facility_id", "opened_at"),
        # Відбір відкритих тривог об'єкта (стрічка тривог, сповіщення).
        Index("ix_alarms_facility_status", "facility_id", "status"),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE")
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("zones.id", ondelete="SET NULL")
    )
    level: Mapped[AlarmLevel] = mapped_column(enum_column(AlarmLevel))
    status: Mapped[AlarmStatus] = mapped_column(
        enum_column(AlarmStatus), default=AlarmStatus.OPEN
    )
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    is_false: Mapped[bool | None] = mapped_column(Boolean)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    events: Mapped[list["AlarmEvent"]] = relationship(
        back_populates="alarm", cascade="all, delete-orphan"
    )
    acknowledgements: Mapped[list["AlarmAcknowledgement"]] = relationship(
        back_populates="alarm"
    )


class AlarmEvent(Base):
    """Зв'язок тривоги з подіями, що її спричинили (багато до багатьох)."""

    __tablename__ = "alarm_events"

    alarm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alarms.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    alarm: Mapped[Alarm] = relationship(back_populates="events")


class AlarmAcknowledgement(UUIDPrimaryKeyMixin, Base):
    """Журнал підтверджень тривог (лише додавання записів)."""

    __tablename__ = "alarm_acknowledgements"

    alarm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alarms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[AckAction] = mapped_column(enum_column(AckAction))
    auth_method: Mapped[AuthMethod] = mapped_column(enum_column(AuthMethod))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    alarm: Mapped[Alarm] = relationship(back_populates="acknowledgements")


class ArmingLogEntry(Base):
    """Журнал постановки на охорону та зняття з охорони (лише додавання)."""

    __tablename__ = "arming_log"
    __table_args__ = (
        Index("ix_arming_log_facility_created", "facility_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE")
    )
    # Порожнє значення означає автоматичну дію системи (розклад, таймер).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    from_mode: Mapped[FacilityMode] = mapped_column(
        enum_column(FacilityMode, name="arming_from_mode")
    )
    to_mode: Mapped[FacilityMode] = mapped_column(
        enum_column(FacilityMode, name="arming_to_mode")
    )
    source: Mapped[ActionSource] = mapped_column(enum_column(ActionSource))
    auth_method: Mapped[AuthMethod | None] = mapped_column(enum_column(AuthMethod))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IncidentSummary(UUIDPrimaryKeyMixin, Base):
    """Стисла хронологія інциденту, сформована мовною моделлю."""

    __tablename__ = "incident_summaries"

    alarm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alarms.id", ondelete="CASCADE"), index=True
    )
    language: Mapped[str] = mapped_column(String(8))
    # Факти містять посилання на номери подій; припущення подаються окремо.
    facts: Mapped[str] = mapped_column(Text)
    assumptions: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TestScenario(UUIDPrimaryKeyMixin, Base):
    """Тестовий сценарій для відтворення: послідовність станів датчиків."""

    __tablename__ = "test_scenarios"
    # Назва починається з Test, але це не клас pytest.
    __test__ = False

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    # [{"offset_ms": 0, "sensor_id": "...", "state": "opened"}, ...]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Очікувані тривоги: [{"level": "confirmed", "zone": "..."}, ...]
    expected: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    runs: Mapped[list["ScenarioRun"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )


class ScenarioRun(UUIDPrimaryKeyMixin, Base):
    """Результат одного відтворення тестового сценарію."""

    __tablename__ = "scenario_runs"

    scenario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("test_scenarios.id", ondelete="CASCADE"), index=True
    )
    passed: Mapped[bool] = mapped_column(Boolean)
    actual: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # Розбіжності між очікуваними й отриманими тривогами.
    mismatches: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    scenario: Mapped[TestScenario] = relationship(back_populates="runs")
