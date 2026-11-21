"""IoT-вузли, датчики та черга команд для вузлів."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import CommandStatus, CommandType, NodeStatus, SensorType


class Node(UUIDPrimaryKeyMixin, Base):
    """IoT-вузол (ESP32), підключений до об'єкта."""

    __tablename__ = "nodes"
    __table_args__ = (
        CheckConstraint("debounce_ms > 0", name="debounce_positive"),
        CheckConstraint("pir_lockout_s >= 0", name="pir_lockout_non_negative"),
        CheckConstraint("config_version > 0", name="config_version_positive"),
    )

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    serial: Mapped[str] = mapped_column(String(64), unique=True)
    # Зберігається лише хеш токена пристрою; сам токен видається один раз.
    device_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    # Ключ підпису команд (HMAC-SHA256). Зберігається відкрито, бо сервер
    # підписує ним команди; вузлу видається один раз під час введення.
    command_key: Mapped[bytes | None] = mapped_column(LargeBinary(32))
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[NodeStatus] = mapped_column(
        enum_column(NodeStatus), default=NodeStatus.PROVISIONING
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Налаштування вузла (ІК-2, ІК-3) і версія конфігурації (ІК-8).
    debounce_ms: Mapped[int] = mapped_column(Integer, default=50)
    pir_lockout_s: Mapped[int] = mapped_column(Integer, default=10)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    sensors: Mapped[list["Sensor"]] = relationship(
        back_populates="node", cascade="all, delete-orphan"
    )


class Sensor(UUIDPrimaryKeyMixin, Base):
    """Датчик, підключений до каналу вузла й закріплений за зоною."""

    __tablename__ = "sensors"
    __table_args__ = (
        UniqueConstraint("node_id", "channel", name="uq_sensors_node_channel"),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("zones.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    sensor_type: Mapped[SensorType] = mapped_column(enum_column(SensorType))
    channel: Mapped[int] = mapped_column(SmallInteger)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    node: Mapped[Node] = relationship(back_populates="sensors")


class NodeCommand(UUIDPrimaryKeyMixin, Base):
    """Підписана команда сервера для вузла (ІК-7).

    Видається у відповіді heartbeat, доки вузол її не підтвердить або не
    мине строк дії. Одноразове число строго зростає в межах вузла.
    """

    __tablename__ = "node_commands"
    __table_args__ = (
        UniqueConstraint("node_id", "nonce", name="uq_node_commands_node_nonce"),
    )

    node_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("nodes.id", ondelete="CASCADE"), index=True
    )
    command_type: Mapped[CommandType] = mapped_column(enum_column(CommandType))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    nonce: Mapped[int] = mapped_column(BigInteger)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[CommandStatus] = mapped_column(
        enum_column(CommandStatus), default=CommandStatus.PENDING
    )
