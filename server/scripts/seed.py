"""Початкові дані для розробки та демонстрації.

Створює користувачів усіх ролей, демо-об'єкт із зонами, вузлом, датчиками
та розкладом. Пароль демо-користувачів береться зі змінної середовища
SEED_PASSWORD; якщо її немає, генерується випадковий і виводиться один раз.
Токен демо-вузла також виводиться один раз (у БД зберігається лише хеш).

Запуск із каталогу server:
    python -m scripts.seed
"""

import os
import secrets
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.devices import Node, Sensor
from app.models.enums import FacilityRole, ScheduleAction, SensorType, ZoneType
from app.models.facilities import (
    Facility,
    FacilityMember,
    FacilitySettings,
    Schedule,
    Zone,
)
from app.models.users import TariffPlan, User
from app.security import generate_token, hash_password, hash_token

DEMO_DOMAIN = "oberih.local"
# Пошта -> (повне ім'я, роль на демо-об'єкті або None, тариф).
DEMO_USERS: dict[str, tuple[str, FacilityRole | None, str]] = {
    "owner": ("Олена Власник", FacilityRole.OWNER, "standard"),
    "family": ("Петро Родина", FacilityRole.FAMILY, "basic"),
    "guest": ("Ірина Гість", FacilityRole.GUEST, "basic"),
    "installer": ("Максим Монтажник", FacilityRole.INSTALLER, "professional"),
    "admin": ("Адміністратор платформи", None, "basic"),
}
# Канал вузла -> (назва датчика, тип, назва зони).
DEMO_SENSORS = {
    1: ("Геркон вхідних дверей", SensorType.REED, "Вхідні двері"),
    2: ("Геркон вікна кухні", SensorType.REED, "Вікно кухні"),
    3: ("PIR вітальні", SensorType.PIR, "Вітальня"),
    4: ("Кнопка корпусу", SensorType.TAMPER, "Корпус вузла"),
}
DEMO_ZONES = {
    "Вхідні двері": ZoneType.PERIMETER,
    "Вікно кухні": ZoneType.PERIMETER,
    "Вітальня": ZoneType.INTERIOR,
    "Корпус вузла": ZoneType.ALWAYS_ON,
}
WEEKDAYS_MASK = 0b0011111  # понеділок — п'ятниця


def seed(db: Session, password: str) -> str | None:
    """Створює демо-дані; повертає токен вузла або None, якщо дані вже є."""
    owner_email = f"owner@{DEMO_DOMAIN}"
    if db.scalar(select(User.id).where(User.email == owner_email)):
        return None

    tariffs = {plan.code: plan for plan in db.scalars(select(TariffPlan))}
    now = datetime.now(UTC)
    password_hash = hash_password(password)
    users: dict[str, User] = {}
    for login, (full_name, _, tariff) in DEMO_USERS.items():
        users[login] = User(
            email=f"{login}@{DEMO_DOMAIN}",
            password_hash=password_hash,
            full_name=full_name,
            tariff_plan=tariffs[tariff],
            privacy_consent_at=now,
            is_platform_admin=login == "admin",
        )
    db.add_all(users.values())
    db.flush()

    facility = Facility(
        name="Демо-квартира",
        address="м. Харків, просп. Науки, 14",
        owner_id=users["owner"].id,
    )
    facility.settings = FacilitySettings()
    for login, (_, role, _) in DEMO_USERS.items():
        if role is None:
            continue
        member = FacilityMember(user_id=users[login].id, role=role)
        if role == FacilityRole.GUEST:
            member.access_from = now
            member.access_until = now + timedelta(days=7)
        facility.members.append(member)
    db.add(facility)
    db.flush()

    zones = {
        name: Zone(facility_id=facility.id, name=name, zone_type=zone_type)
        for name, zone_type in DEMO_ZONES.items()
    }
    db.add_all(zones.values())
    db.flush()

    token = generate_token()
    node = Node(
        facility_id=facility.id,
        name="Вузол передпокою",
        serial="ESP32-DEMO-001",
        device_token_hash=hash_token(token),
        commissioned_at=now,
    )
    for channel, (name, sensor_type, zone_name) in DEMO_SENSORS.items():
        node.sensors.append(
            Sensor(
                zone_id=zones[zone_name].id,
                name=name,
                sensor_type=sensor_type,
                channel=channel,
            )
        )
    db.add(node)
    db.add(
        Schedule(
            facility_id=facility.id,
            name="Робочі дні",
            action=ScheduleAction.ARM_AWAY,
            days_mask=WEEKDAYS_MASK,
            local_time=time(9, 0),
        )
    )
    db.commit()
    return token


def main() -> None:
    """Точка входу командного рядка."""
    password = os.environ.get("SEED_PASSWORD")
    generated = password is None
    if password is None:
        password = secrets.token_urlsafe(9)
    with SessionLocal() as db:
        token = seed(db, password)
    if token is None:
        print("Демо-дані вже створено, нічого не змінено.")
        return
    print("Демо-дані створено. Користувачі:")
    for login, (_, role, tariff) in DEMO_USERS.items():
        label = role.value if role else "platform admin"
        email = f"{login}@{DEMO_DOMAIN}"
        print(f"  {email:<24} {label:<15} тариф {tariff}")
    if generated:
        print(f"Пароль усіх демо-користувачів (показується один раз): {password}")
    print(f"Токен пристрою ESP32-DEMO-001 (показується один раз): {token}")


if __name__ == "__main__":
    main()
