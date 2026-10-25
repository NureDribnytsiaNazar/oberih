"""Повторне підтвердження чутливих дій (зняття з охорони, дії з тривогою)."""

from app.errors import UnauthorizedError
from app.models.enums import AuthMethod
from app.models.users import User
from app.schemas.common import Confirmation
from app.security import verify_password, verify_totp


def confirm_action(user: User, confirmation: Confirmation | None) -> AuthMethod:
    """Перевіряє пароль або код TOTP і повертає використаний спосіб."""
    if confirmation is None:
        raise UnauthorizedError("reauth_required")
    if confirmation.method == AuthMethod.PASSWORD:
        valid = verify_password(confirmation.value, user.password_hash)
    elif confirmation.method == AuthMethod.TOTP:
        valid = (
            user.totp_enabled
            and user.totp_secret is not None
            and verify_totp(user.totp_secret, confirmation.value)
        )
    else:
        # PIN і біометрія перевіряються на мобільному пристрої (не в ЛБ2).
        valid = False
    if not valid:
        raise UnauthorizedError("reauth_failed")
    return confirmation.method
