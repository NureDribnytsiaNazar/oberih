"""Реєстрація, вхід, оновлення токенів і двофакторна автентифікація."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import BadRequestError, ConflictError, UnauthorizedError
from app.models.users import RefreshToken, TariffPlan, User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair, TotpSetup
from app.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    new_totp_secret,
    totp_uri,
    verify_password,
    verify_totp,
)
from app.services import audit

# Новий користувач отримує безкоштовний тариф (таблиця 4 Vision & Scope).
DEFAULT_TARIFF_CODE = "basic"


def register(db: Session, data: RegisterRequest) -> User:
    """Створює обліковий запис із безкоштовним тарифом."""
    if not data.privacy_consent:
        raise BadRequestError("consent_required")
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise ConflictError("email_taken")
    tariff = db.scalars(
        select(TariffPlan).where(TariffPlan.code == DEFAULT_TARIFF_CODE)
    ).one()
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        locale=data.locale,
        tariff_plan=tariff,
        privacy_consent_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    audit.record(db, user.id, "user.register", "user", user.id)
    db.commit()
    return user


def login(db: Session, data: LoginRequest, user_agent: str | None) -> TokenPair:
    """Перевіряє облікові дані та видає пару токенів."""
    user = db.scalar(select(User).where(User.email == data.email))
    # Однакова відповідь для невідомої пошти й неправильного пароля.
    if (
        user is None
        or not user.is_active
        or not verify_password(data.password, user.password_hash)
    ):
        raise UnauthorizedError("invalid_credentials")
    if user.totp_enabled:
        if data.totp_code is None:
            raise UnauthorizedError("totp_required")
        if user.totp_secret is None or not verify_totp(
            user.totp_secret, data.totp_code
        ):
            raise UnauthorizedError("totp_invalid")
    tokens = _issue_tokens(db, user, user_agent)
    audit.record(db, user.id, "user.login", "user", user.id)
    db.commit()
    return tokens


def refresh(db: Session, refresh_token: str, user_agent: str | None) -> TokenPair:
    """Обмінює токен оновлення на нову пару (старий токен відкликається)."""
    stored = _find_active_refresh_token(db, refresh_token)
    if stored is None or not stored.user.is_active:
        raise UnauthorizedError("invalid_token")
    stored.revoked_at = datetime.now(UTC)
    tokens = _issue_tokens(db, stored.user, user_agent)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str) -> None:
    """Відкликає токен оновлення (повторний вихід не є помилкою)."""
    stored = _find_active_refresh_token(db, refresh_token)
    if stored is not None:
        stored.revoked_at = datetime.now(UTC)
        db.commit()


def start_totp(db: Session, user: User) -> TotpSetup:
    """Генерує новий секрет TOTP; 2FA вмикається після перевірки коду."""
    user.totp_secret = new_totp_secret()
    user.totp_enabled = False
    db.commit()
    return TotpSetup(
        secret=user.totp_secret, otpauth_uri=totp_uri(user.totp_secret, user.email)
    )


def confirm_totp(db: Session, user: User, code: str) -> None:
    """Вмикає 2FA, якщо код із застосунку-автентифікатора правильний."""
    if user.totp_secret is None:
        raise BadRequestError("totp_not_initialized")
    if not verify_totp(user.totp_secret, code):
        raise UnauthorizedError("totp_invalid")
    user.totp_enabled = True
    audit.record(db, user.id, "user.totp_enabled", "user", user.id)
    db.commit()


def _issue_tokens(db: Session, user: User, user_agent: str | None) -> TokenPair:
    refresh_token = generate_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        expires_in=settings.access_token_minutes * 60,
    )


def _find_active_refresh_token(db: Session, token: str) -> RefreshToken | None:
    return db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_token(token),
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
