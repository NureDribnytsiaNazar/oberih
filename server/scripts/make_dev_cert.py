"""Самопідписаний TLS-сертифікат сервера для демонстрації з вузлом у Wokwi.

Навіщо: тунелі, що самі завершують TLS (Cloudflare Quick Tunnel), рвуть
рукопожаття, якщо клієнт рахує його довше ~10 с, а ESP32 у симуляторі Wokwi
рахує ~11 с. Тому TLS завершує сам сервер (uvicorn або Nginx, таймаут
рукопожаття 60 с), а TCP-тунель (bore) лише пересилає байти. Вузол довіряє
саме цьому сертифікату (provision_node --ca-file).

Ключ RSA-2048: на ESP32 перевірка підпису RSA значно дешевша за ECDSA.
Файли в git не потрапляють (*.crt, *.key у .gitignore).

Запуск із каталогу server:
    python -m scripts.make_dev_cert --names bore.pub localhost
"""

import argparse
import ipaddress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "certs"
KEY_BITS = 2048
VALID_DAYS = 365


def make_certificate(names: list[str]) -> tuple[bytes, bytes]:
    """Пара (сертифікат PEM, ключ PEM) з іменами names і 127.0.0.1 у SAN."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_BITS)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0])])
    alt_names: list[x509.GeneralName] = [x509.DNSName(name) for name in names]
    alt_names.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def main() -> None:
    """Точка входу командного рядка."""
    parser = argparse.ArgumentParser(description="Самопідписаний сертифікат")
    parser.add_argument("--names", nargs="+", default=["bore.pub", "localhost"])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    cert_pem, key_pem = make_certificate(args.names)
    args.dir.mkdir(parents=True, exist_ok=True)
    (args.dir / "server.crt").write_bytes(cert_pem)
    (args.dir / "server.key").write_bytes(key_pem)
    print(f"Сертифікат: {args.dir / 'server.crt'} ({', '.join(args.names)})")


if __name__ == "__main__":
    main()
