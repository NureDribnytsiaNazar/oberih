"""Перелічення (допустимі значення) для полів моделей предметної області."""

import enum


class Locale(str, enum.Enum):
    """Мова інтерфейсу користувача."""

    UK = "uk"
    EN = "en"


class TimeFormat(str, enum.Enum):
    """Формат відображення часу в клієнтах."""

    H24 = "24h"
    H12 = "12h"


class MeasurementSystem(str, enum.Enum):
    """Система мір для відображення величин."""

    METRIC = "metric"
    IMPERIAL = "imperial"


class FacilityMode(str, enum.Enum):
    """Режими охорони об'єкта (автомат станів, рисунок 2 у Vision & Scope)."""

    DISARMED = "disarmed"
    EXIT_DELAY = "exit_delay"
    ARMED_AWAY = "armed_away"
    ARMED_HOME = "armed_home"
    ENTRY_DELAY = "entry_delay"
    ALARM = "alarm"


class FacilityRole(str, enum.Enum):
    """Роль користувача на конкретному об'єкті (таблиця 7)."""

    OWNER = "owner"
    FAMILY = "family"
    GUEST = "guest"
    INSTALLER = "installer"


class ZoneType(str, enum.Enum):
    """Тип зони: периметральна, внутрішня або цілодобова."""

    PERIMETER = "perimeter"
    INTERIOR = "interior"
    ALWAYS_ON = "always_on"


class SensorType(str, enum.Enum):
    """Тип датчика (від типу залежить вага в індексі достовірності)."""

    REED = "reed"
    PIR = "pir"
    TAMPER = "tamper"


class NodeStatus(str, enum.Enum):
    """Стан IoT-вузла."""

    PROVISIONING = "provisioning"
    ONLINE = "online"
    OFFLINE = "offline"
    DISABLED = "disabled"


class EventType(str, enum.Enum):
    """Тип події, що надходить від вузла або формується сервером."""

    OPENED = "opened"
    CLOSED = "closed"
    MOTION = "motion"
    TAMPER = "tamper"
    TAMPER_RESTORED = "tamper_restored"
    NODE_OFFLINE = "node_offline"
    NODE_ONLINE = "node_online"


class AlarmLevel(str, enum.Enum):
    """Класифікація тривоги за індексом достовірності."""

    WARNING = "warning"
    ALARM = "alarm"
    CONFIRMED = "confirmed"


class AlarmStatus(str, enum.Enum):
    """Стан обробки тривоги."""

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    # Скасована: охорону знято під час затримки входу (законний вхід).
    CANCELLED = "cancelled"


class AckAction(str, enum.Enum):
    """Дія користувача щодо тривоги."""

    ACKNOWLEDGE = "acknowledge"
    MARK_FALSE = "mark_false"
    RESOLVE = "resolve"


class AuthMethod(str, enum.Enum):
    """Спосіб повторного підтвердження чутливої дії."""

    PASSWORD = "password"
    TOTP = "totp"
    PIN = "pin"
    BIOMETRIC = "biometric"


class ActionSource(str, enum.Enum):
    """Джерело команди керування охороною."""

    WEB = "web"
    MOBILE = "mobile"
    DEVICE = "device"
    SCHEDULE = "schedule"
    SYSTEM = "system"
    API = "api"


class ScheduleAction(str, enum.Enum):
    """Дія, яку виконує розклад."""

    ARM_AWAY = "arm_away"
    ARM_HOME = "arm_home"
    DISARM = "disarm"


class NotificationChannel(str, enum.Enum):
    """Канал доставки сповіщень."""

    PUSH = "push"
    EMAIL = "email"


class PushPlatform(str, enum.Enum):
    """Платформа клієнта, що отримує push-повідомлення."""

    ANDROID = "android"
    WEB = "web"


class BackupKind(str, enum.Enum):
    """Вміст резервної копії."""

    FULL = "full"
    SETTINGS = "settings"


class BackupStatus(str, enum.Enum):
    """Стан створення резервної копії."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CommandType(str, enum.Enum):
    """Команда сервера для IoT-вузла (ІК-7)."""

    ARM_AWAY = "arm_away"
    ARM_HOME = "arm_home"
    DISARM = "disarm"
    SET_CONFIG = "set_config"


class CommandStatus(str, enum.Enum):
    """Стан доставки команди вузлу."""

    PENDING = "pending"  # у черзі, ще не видавалася
    DELIVERED = "delivered"  # видана у відповіді heartbeat, чекає підтвердження
    ACKED = "acked"  # вузол підтвердив отримання
    EXPIRED = "expired"  # строк дії минув до підтвердження


class CertificateStatus(str, enum.Enum):
    """Стан сертифіката."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
