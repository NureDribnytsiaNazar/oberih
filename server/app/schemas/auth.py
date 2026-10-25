"""Схеми автентифікації: реєстрація, вхід, токени, TOTP."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import Locale
from app.schemas.common import Email, Name

Password = Annotated[str, Field(min_length=8, max_length=128)]
TotpCode = Annotated[str, StringConstraints(pattern=r"^\d{6}$")]


class RegisterRequest(BaseModel):
    """Дані для створення облікового запису."""

    email: Email
    password: Password
    full_name: Annotated[Name, Field(max_length=128)]
    locale: Locale = Locale.UK
    privacy_consent: bool = Field(
        description="Згода на обробку персональних даних (GDPR)"
    )


class LoginRequest(BaseModel):
    """Вхід за електронною поштою й паролем (і кодом TOTP, якщо 2FA увімкнено)."""

    email: Email
    password: Annotated[str, Field(max_length=128)]
    totp_code: TotpCode | None = None


class TokenPair(BaseModel):
    """Токен доступу (JWT) і токен оновлення."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Час життя токена доступу, с")


class RefreshRequest(BaseModel):
    """Токен оновлення для отримання нової пари або виходу."""

    refresh_token: Annotated[str, Field(min_length=1, max_length=256)]


class TotpSetup(BaseModel):
    """Секрет TOTP для додавання в застосунок-автентифікатор."""

    secret: str
    otpauth_uri: str


class TotpVerifyRequest(BaseModel):
    """Код із застосунку-автентифікатора."""

    code: TotpCode
