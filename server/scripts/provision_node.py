"""Повторне введення вузла в експлуатацію та запис секретів для прошивки.

Видає вузлу новий токен пристрою й ключ підпису команд (попередні стають
недійсними) і записує їх разом з адресою сервера у файл iot/include/secrets.h.
Файл не потрапляє в git (.gitignore). Скрипт працює напряму з БД, тому
його запускає адміністратор на машині сервера.

Запуск із каталогу server:
    python -m scripts.provision_node --serial ESP32-DEMO-001 \\
        --server-url https://example.trycloudflare.com
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.devices import Node
from app.models.enums import NodeStatus
from app.security import generate_token, hash_token
from app.services import audit, commands

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "iot" / "include" / "secrets.h"


def provision(db: Session, serial: str) -> tuple[Node, str, bytes]:
    """Видає новий токен і ключ вузлу з серійним номером serial."""
    node = db.scalar(select(Node).where(Node.serial == serial))
    if node is None:
        raise SystemExit(f"Вузол із серійним номером {serial} не знайдено")
    token = generate_token()
    key = commands.new_command_key()
    node.device_token_hash = hash_token(token)
    node.command_key = key
    node.commissioned_at = datetime.now(UTC)
    node.status = NodeStatus.PROVISIONING
    audit.record(db, None, "node.commission", "node", node.id, {"via": "script"})
    db.commit()
    return node, token, key


def render_secrets(node: Node, token: str, key: bytes, server_url: str) -> str:
    """Вміст secrets.h для прошивки."""
    return (
        "// Згенеровано server/scripts/provision_node.py. Не комітити!\n"
        "#pragma once\n\n"
        f'#define OBERIH_SERVER_URL "{server_url}"\n'
        f'#define OBERIH_NODE_ID "{node.id}"\n'
        f'#define OBERIH_DEVICE_TOKEN "{token}"\n'
        f'#define OBERIH_COMMAND_KEY "{key.hex()}"\n'
    )


def main() -> None:
    """Точка входу командного рядка."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--serial", default="ESP32-DEMO-001")
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    with SessionLocal() as db:
        node, token, key = provision(db, args.serial)
        content = render_secrets(node, token, key, args.server_url.rstrip("/"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Вузол {args.serial} ({node.id}) введено повторно.")
    print(f"Секрети записано у {args.output}")


if __name__ == "__main__":
    main()
