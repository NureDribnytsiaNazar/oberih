"""Повторне введення вузла в експлуатацію та запис секретів для прошивки.

Видає вузлу новий токен пристрою й ключ підпису команд (попередні стають
недійсними) і записує їх разом з адресою сервера у файл iot/include/secrets.h.
Для HTTPS-адреси скрипт також бере з перевіреного ланцюжка TLS сервера
(тунелю) сертифікат-якір довіри й вписує його як OBERIH_CA_CERT для
setCACert на ESP32. За замовчуванням якір — безпосередній видавець
сертифіката сервера (--ca-level issuer): тоді mbedTLS перевіряє лише один
підпис, і рукопожаття встигає в симуляторі Wokwi. --ca-level root вписує
корінь (повна перевірка ланцюжка, для справжньої плати). --no-ca пропускає
цей крок (тоді прошивку збирають у середовищі esp32dev_devtls).
Файл не потрапляє в git (.gitignore). Скрипт працює напряму з БД, тому
його запускає адміністратор на машині сервера.

Запуск із каталогу server:
    python -m scripts.provision_node --serial ESP32-DEMO-001 \\
        --server-url https://example.trycloudflare.com
"""

import argparse
import socket
import ssl
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.devices import Node
from app.models.enums import NodeStatus
from app.security import generate_token, hash_token
from app.services import audit, commands

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "iot" / "include" / "secrets.h"
HTTPS_PORT = 443
CONNECT_TIMEOUT_S = 10


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


def fetch_ca_cert(server_url: str, level: str = "issuer") -> str:
    """PEM сертифіката-якоря з перевіреного ланцюжка сервера.

    Ланцюжок перевіряється системним сховищем довірених сертифікатів:
    [0] — сертифікат сервера, [1] — його видавець, [-1] — корінь.
    """
    parts = urlsplit(server_url)
    host = parts.hostname
    if parts.scheme != "https" or host is None:
        raise SystemExit("Кореневий сертифікат визначається лише для https://")
    context = ssl.create_default_context()
    address = (host, parts.port or HTTPS_PORT)
    with socket.create_connection(address, timeout=CONNECT_TIMEOUT_S) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            chain = tls.get_verified_chain()
    # SSLSocket повертає ланцюжок як список сертифікатів у форматі DER.
    anchor = chain[1] if level == "issuer" and len(chain) > 1 else chain[-1]
    return ssl.DER_cert_to_PEM_cert(anchor)


def c_string(text: str) -> str:
    """Багаторядковий текст як рядковий літерал C (рядки через \\n)."""
    lines = [f'  "{line}\\n"' for line in text.strip().splitlines()]
    return " \\\n".join(lines)


def render_secrets(
    node: Node,
    token: str,
    key: bytes,
    server_url: str,
    ca_cert: str | None = None,
) -> str:
    """Вміст secrets.h для прошивки."""
    content = (
        "// Згенеровано server/scripts/provision_node.py. Не комітити!\n"
        "#pragma once\n\n"
        f'#define OBERIH_SERVER_URL "{server_url}"\n'
        f'#define OBERIH_NODE_ID "{node.id}"\n'
        f'#define OBERIH_DEVICE_TOKEN "{token}"\n'
        f'#define OBERIH_COMMAND_KEY "{key.hex()}"\n'
    )
    if ca_cert:
        content += f"#define OBERIH_CA_CERT \\\n{c_string(ca_cert)}\n"
    return content


def main() -> None:
    """Точка входу командного рядка."""
    parser = argparse.ArgumentParser(description="Секрети вузла для прошивки")
    parser.add_argument("--serial", default="ESP32-DEMO-001")
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--ca-level",
        choices=("issuer", "root"),
        default="issuer",
        help="якір довіри: видавець сертифіката сервера або корінь ланцюжка",
    )
    parser.add_argument(
        "--no-ca", action="store_true", help="не вписувати сертифікат-якір"
    )
    args = parser.parse_args()
    server_url = args.server_url.rstrip("/")
    ca_cert = None if args.no_ca else fetch_ca_cert(server_url, args.ca_level)
    with SessionLocal() as db:
        node, token, key = provision(db, args.serial)
        content = render_secrets(node, token, key, server_url, ca_cert)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Вузол {args.serial} ({node.id}) введено повторно.")
    print(f"Секрети записано у {args.output}")
    if ca_cert is None:
        print("Без сертифіката-якоря: збирайте esp32dev_devtls.")


if __name__ == "__main__":
    main()
