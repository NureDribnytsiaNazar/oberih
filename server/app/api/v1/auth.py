"""Маршрути автентифікації."""

from typing import Annotated

from fastapi import APIRouter, Header, status

from app.deps import CurrentUser, DbSession
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    TotpSetup,
    TotpVerifyRequest,
)
from app.schemas.users import UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

UserAgent = Annotated[str | None, Header()]


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: DbSession) -> object:
    """Реєстрація користувача (потрібна згода на обробку даних)."""
    return auth_service.register(db, data)


@router.post("/login")
def login(data: LoginRequest, db: DbSession, user_agent: UserAgent = None) -> TokenPair:
    """Вхід; за увімкненої 2FA потрібен ще й код TOTP."""
    return auth_service.login(db, data, user_agent)


@router.post("/refresh")
def refresh(
    data: RefreshRequest, db: DbSession, user_agent: UserAgent = None
) -> TokenPair:
    """Нова пара токенів за токеном оновлення (старий відкликається)."""
    return auth_service.refresh(db, data.refresh_token, user_agent)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(data: RefreshRequest, db: DbSession) -> None:
    """Вихід: відкликання токена оновлення."""
    auth_service.logout(db, data.refresh_token)


@router.post("/totp/enable")
def totp_enable(user: CurrentUser, db: DbSession) -> TotpSetup:
    """Початок налаштування 2FA: видається секрет для автентифікатора."""
    return auth_service.start_totp(db, user)


@router.post("/totp/verify", status_code=status.HTTP_204_NO_CONTENT)
def totp_verify(data: TotpVerifyRequest, user: CurrentUser, db: DbSession) -> None:
    """Завершення налаштування 2FA: перевірка першого коду."""
    auth_service.confirm_totp(db, user, data.code)
