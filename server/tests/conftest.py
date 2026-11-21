"""Спільні фікстури тестів.

Тести працюють з окремою БД <назва>_test у тому самому PostgreSQL
(контейнер oberih-db). Схема створюється міграціями Alembic, тому тести
перевіряють і самі міграції. Перед кожним тестом таблиці очищаються.
"""

import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Секрет JWT потрібен до імпорту застосунку; у тестах достатньо випадкового.
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))
# Фоновий виконавець у тестах вимкнено: таймери викликаються явно з now.
os.environ["WORKER_ENABLED"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine, make_url  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import get_db, make_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402

SERVER_DIR = Path(__file__).resolve().parent.parent
API = "/api/v1"
PASSWORD = "Correct-Horse-9"
# Таблиці, які не очищаються між тестами: довідник тарифів і версія схеми.
KEEP_TABLES = {"tariff_plans"}


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(settings.database_url)
    return url.set(database=f"{url.database}_test").render_as_string(
        hide_password=False
    )


def _create_database(url: str) -> None:
    target = make_url(url)
    admin_engine = make_engine(
        target.set(database="postgres").render_as_string(hide_password=False)
    )
    with admin_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": target.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Чиста тестова БД, створена міграціями.

    Схема перестворюється з нуля, після чого міграції застосовуються,
    повністю відкочуються й застосовуються знову — так перевіряються обидва
    напрями кожної міграції.
    """
    url = _test_database_url()
    _create_database(url)
    test_engine = make_engine(url)
    with test_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    config = Config(str(SERVER_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(SERVER_DIR / "alembic"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> sessionmaker[Session]:
    """Очищає дані перед тестом і повертає фабрику сесій тестової БД."""
    tables = ", ".join(
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in KEEP_TABLES
    )
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Сесія для прямих запитів до БД у тестах."""
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    """HTTP-клієнт застосунку, підключеного до тестової БД."""

    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Допоміжні функції сценаріїв ---------------------------------------------


def register(client: TestClient, email: str, **extra: Any) -> dict[str, Any]:
    """Реєструє користувача й повертає його профіль."""
    body = {
        "email": email,
        "password": PASSWORD,
        "full_name": email.split("@")[0],
        "privacy_consent": True,
        **extra,
    }
    response = client.post(f"{API}/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, email: str, **extra: Any) -> dict[str, str]:
    """Входить і повертає заголовок Authorization."""
    response = client.post(
        f"{API}/auth/login", json={"email": email, "password": PASSWORD, **extra}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def new_user(client: TestClient, email: str) -> dict[str, str]:
    """Реєструє користувача й повертає заголовки для його запитів."""
    register(client, email)
    return login(client, email)


def set_tariff(db: Session, email: str, code: str) -> None:
    """Переводить користувача на інший тариф (оплата — поза межами ЛБ2)."""
    db.execute(
        text(
            "UPDATE users SET tariff_plan_id = "
            "(SELECT id FROM tariff_plans WHERE code = :code) WHERE email = :email"
        ),
        {"code": code, "email": email},
    )
    db.commit()


def create_facility(client: TestClient, headers: dict[str, str]) -> str:
    """Створює об'єкт і повертає його ідентифікатор."""
    response = client.post(
        f"{API}/facilities", json={"name": "Квартира"}, headers=headers
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def add_member(
    client: TestClient,
    owner: dict[str, str],
    facility_id: str,
    email: str,
    role: str,
    **extra: Any,
) -> dict[str, Any]:
    """Додає користувача до об'єкта з роллю."""
    response = client.post(
        f"{API}/facilities/{facility_id}/members",
        json={"email": email, "role": role, **extra},
        headers=owner,
    )
    assert response.status_code == 201, response.text
    return response.json()


def confirmation() -> dict[str, str]:
    """Повторне підтвердження чутливої дії паролем."""
    return {"method": "password", "value": PASSWORD}


@pytest.fixture()
def owner(client: TestClient) -> dict[str, str]:
    """Заголовки власника об'єкта."""
    return new_user(client, "owner@test.ua")


@pytest.fixture()
def facility_id(client: TestClient, owner: dict[str, str]) -> str:
    """Об'єкт власника."""
    return create_facility(client, owner)


@pytest.fixture()
def device(
    client: TestClient, owner: dict[str, str], facility_id: str
) -> dict[str, Any]:
    """Вузол у експлуатації з герконом (канал 1), PIR (2) і тампером (3)."""
    return make_device(client, owner, facility_id, "ESP32-0001")


@pytest.fixture()
def second_device(client: TestClient) -> dict[str, Any]:
    """Вузол іншого власника на іншому об'єкті."""
    other = new_user(client, "other-owner@test.ua")
    return make_device(client, other, create_facility(client, other), "ESP32-0002")


def make_device(
    client: TestClient, owner: dict[str, str], facility_id: str, serial: str
) -> dict[str, Any]:
    """Створює зони, вузол із трьома датчиками й вводить його в експлуатацію."""
    base = f"{API}/facilities/{facility_id}"
    zones = {}
    for name, zone_type in (
        ("Вхідні двері", "perimeter"),
        ("Вітальня", "interior"),
        ("Корпус", "always_on"),
    ):
        response = client.post(
            f"{base}/zones", json={"name": name, "zone_type": zone_type}, headers=owner
        )
        zones[zone_type] = response.json()["id"]
    node = client.post(
        f"{base}/nodes", json={"name": "Вузол 1", "serial": serial}, headers=owner
    ).json()
    for channel, sensor_type, zone_type in (
        (1, "reed", "perimeter"),
        (2, "pir", "interior"),
        (3, "tamper", "always_on"),
    ):
        response = client.post(
            f"{base}/nodes/{node['id']}/sensors",
            json={
                "zone_id": zones[zone_type],
                "name": sensor_type,
                "sensor_type": sensor_type,
                "channel": channel,
            },
            headers=owner,
        )
        assert response.status_code == 201, response.text
    commission = client.post(
        f"{base}/nodes/{node['id']}/commission", headers=owner
    ).json()
    return {
        "node_id": node["id"],
        "zones": zones,
        "headers": {"X-Device-Token": commission["device_token"]},
        "command_key": commission["command_key"],
    }
