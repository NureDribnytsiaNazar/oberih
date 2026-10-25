"""IoT-вузли та датчики."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDPrimaryKeyMixin, enum_column
from app.models.enums import NodeStatus, SensorType


class Node(UUIDPrimaryKeyMixin, Base):
    """IoT-вузол (ESP32), підключений до об'єкта."""

    __tablename__ = "nodes"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("facilities.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    serial: Mapped[str] = mapped_column(String(64), unique=True)
    # Зберігається лише хеш токена пристрою; сам токен видається один раз.
    device_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[NodeStatus] = mapped_column(
        enum_column(NodeStatus), default=NodeStatus.PROVISIONING
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    commissioned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
