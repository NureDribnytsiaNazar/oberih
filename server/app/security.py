"""Криптографічні операції: паролі, токени доступу, токени пристроїв, TOTP."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Повертає хеш пароля Argon2 (сам пароль ніде не зберігається)."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Перевіряє пароль за збереженим хешем."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    """Створює короткоживучий JWT доступу для користувача."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID | None:
    """Повертає ідентифікатор користувача з JWT або None, якщо токен недійсний."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


def generate_token() -> str:
    """Генерує випадковий непрозорий токен (оновлення доступу, пристрій)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Хеш SHA-256 токена: у БД зберігається лише він.

    Для випадкових токенів достатньо швидкого хешу, на відміну від паролів,
    які люди обирають самі й тому хешуються повільним Argon2.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def new_totp_secret() -> str:
    """Генерує секрет для одноразових кодів TOTP."""
    return pyotp.random_base32()


def totp_uri(secret: str, email: str) -> str:
    """Посилання otpauth:// для додавання в застосунок-автентифікатор."""
    return pyotp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=settings.totp_issuer
    )


def verify_totp(secret: str, code: str) -> bool:
    """Перевіряє код TOTP із допуском в один 30-секундний інтервал."""
    return pyotp.TOTP(secret).verify(code, valid_window=1)
