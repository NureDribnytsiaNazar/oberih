"""Початкові дані для розробки та демонстрації.

Створює користувачів усіх ролей, демо-об'єкт із зонами, вузлом, датчиками
та розкладом. Пароль демо-користувачів береться зі змінної середовища
SEED_PASSWORD; якщо її немає, генерується випадковий і виводиться один раз.
Токен демо-вузла та ключ підпису команд також виводяться один раз (у БД
зберігається хеш токена). Для прошивки їх зручніше отримати скриптом
scripts/provision_node.py, який записує iot/include/secrets.h.

Для показу ЛБ3 додаються: об'єкт під охороною (armed_away), три закриті
тривоги (дві позначені як хибні), тестовий сценарій і два сертифікати вузла
(чинний і відкликаний). Центр сертифікації створюється в CA_DIR, якщо його
ще немає. Повторний запуск нічого не дублює.

Запуск із каталогу server:
    python -m scripts.seed
"""

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.devices import Node, Sensor
from app.models.enums import (
    AckAction,
    ActionSource,
    AlarmLevel,
    AlarmStatus,
    AuthMethod,
    EventType,
    FacilityMode,
    FacilityRole,
    ScheduleAction,
    SensorType,
    ZoneType,
)
from app.models.events import (
    Alarm,
    AlarmAcknowledgement,
    AlarmEvent,
    Event,
    TestScenario,
)
from app.models.facilities import (
    Facility,
    FacilityMember,
    FacilitySettings,
    Schedule,
    Zone,
)
from app.models.users import TariffPlan, User
from app.security import generate_token, hash_password, hash_token
from app.services import arming, certificates, commands
from app.services.state_machine import ModeTrigger

DEMO_DOMAIN = "oberih.local"
# Пошта -> (повне ім'я, роль на демо-об'єкті або None, тариф).
DEMO_USERS: dict[str, tuple[str, FacilityRole | None, str]] = {
    "owner": ("Олена Власник", FacilityRole.OWNER, "professional"),
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
DEMO_SCENARIO = "Проникнення через вхідні двері"
# Закриті тривоги для статистики FAR: (днів тому, хибна?).
DEMO_ALARMS = ((5, True), (3, True), (1, False))


@dataclass(frozen=True)
class NodeCredentials:
    """Секрети демо-вузла, що показуються один раз."""

    node_id: str
    device_token: str
    command_key: str


def seed(db: Session, password: str) -> NodeCredentials | None:
    """Створює демо-дані; повертає секрети вузла або None, якщо дані вже є."""
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
    command_key = commands.new_command_key()
    node = Node(
        facility_id=facility.id,
        name="Вузол передпокою",
        serial="ESP32-DEMO-001",
        device_token_hash=hash_token(token),
        command_key=command_key,
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
    return NodeCredentials(str(node.id), token, command_key.hex())


def seed_lab3(db: Session) -> bool:
    """Додає демо-дані ЛБ3; повертає False, якщо їх уже створено."""
    facility = db.scalars(
        select(Facility).where(Facility.name == "Демо-квартира")
    ).one()
    exists = select(TestScenario.id).where(
        TestScenario.facility_id == facility.id, TestScenario.name == DEMO_SCENARIO
    )
    if db.scalar(exists) is not None:
        return False
    owner = db.get_one(User, facility.owner_id)
    owner.tariff_plan = db.scalars(
        select(TariffPlan).where(TariffPlan.code == "professional")
    ).one()
    node = db.scalars(select(Node).where(Node.facility_id == facility.id)).first()
    assert node is not None, "demo node is missing"
    sensors = {sensor.channel: sensor for sensor in node.sensors}
    _demo_alarms(db, facility, node, sensors[1], owner)
    db.add(
        TestScenario(
            facility_id=facility.id,
            name=DEMO_SCENARIO,
            description="Двері, потім рух у вітальні через 20 с",
            steps=[
                {"offset_ms": 0, "sensor_id": str(sensors[1].id), "state": "opened"},
                {
                    "offset_ms": 20000,
                    "sensor_id": str(sensors[3].id),
                    "state": "motion",
                },
            ],
            expected=[{"level": "confirmed", "zone_id": None}],
            created_by=owner.id,
        )
    )
    if facility.mode == FacilityMode.DISARMED:
        arming.transition(db, facility, ModeTrigger.ARM_AWAY, ActionSource.SCHEDULE)
        arming.transition(
            db, facility, ModeTrigger.EXIT_DELAY_EXPIRED, ActionSource.SYSTEM
        )
    db.commit()
    _demo_certificates(db, node)
    return True


def _demo_alarms(
    db: Session, facility: Facility, node: Node, door: Sensor, owner: User
) -> None:
    """Закриті тривоги геркона дверей; дві з них позначені як хибні."""
    now = datetime.now(UTC)
    for index, (days_ago, is_false) in enumerate(DEMO_ALARMS, start=1):
        moment = now - timedelta(days=days_ago)
        event = Event(
            facility_id=facility.id,
            node_id=node.id,
            sensor_id=door.id,
            event_type=EventType.OPENED,
            seq=900000 + index,
            occurred_at=moment,
        )
        alarm = Alarm(
            facility_id=facility.id,
            zone_id=door.zone_id,
            level=AlarmLevel.ALARM,
            status=AlarmStatus.RESOLVED,
            confidence=Decimal("0.50"),
            is_false=is_false,
            opened_at=moment,
            closed_at=moment + timedelta(minutes=2),
        )
        db.add_all([event, alarm])
        db.flush()
        db.add(AlarmEvent(alarm_id=alarm.id, event_id=event.id))
        db.add(
            AlarmAcknowledgement(
                alarm_id=alarm.id,
                user_id=owner.id,
                action=AckAction.MARK_FALSE if is_false else AckAction.RESOLVE,
                auth_method=AuthMethod.PASSWORD,
            )
        )


def _demo_certificates(db: Session, node: Node) -> None:
    """Чинний і відкликаний сертифікати вузла (ключі не зберігаються)."""
    if not (settings.ca_dir / certificates.CA_CERT_FILE).exists():
        certificates.create_ca(settings.ca_dir)
    admin = db.scalars(select(User).where(User.is_platform_admin)).first()
    assert admin is not None, "demo admin is missing"
    old = certificates.issue(db, settings.ca_dir, admin, node.id, 365)
    certificates.revoke(db, admin, old.certificate.id)
    certificates.issue(db, settings.ca_dir, admin, node.id, 365)


def main() -> None:
    """Точка входу командного рядка."""
    password = os.environ.get("SEED_PASSWORD")
    generated = password is None
    if password is None:
        password = secrets.token_urlsafe(9)
    with SessionLocal() as db:
        credentials = seed(db, password)
        added_lab3 = seed_lab3(db)
    if credentials is None:
        print("Базові демо-дані вже є.")
        if added_lab3:
            print("Додано демо-дані ЛБ3: тривоги, сценарій, сертифікати.")
        return
    print("Демо-дані створено. Користувачі:")
    for login, (_, role, tariff) in DEMO_USERS.items():
        label = role.value if role else "platform admin"
        email = f"{login}@{DEMO_DOMAIN}"
        print(f"  {email:<24} {label:<15} тариф {tariff}")
    if generated:
        print(f"Пароль усіх демо-користувачів (показується один раз): {password}")
    print("Вузол ESP32-DEMO-001 (секрети показуються один раз):")
    print(f"  node_id      {credentials.node_id}")
    print(f"  device_token {credentials.device_token}")
    print(f"  command_key  {credentials.command_key}")
    if added_lab3:
        print("Додано демо-дані ЛБ3: тривоги, сценарій, сертифікати.")


if __name__ == "__main__":
    main()
