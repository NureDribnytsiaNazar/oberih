"""Залежності FastAPI: сесія БД, поточний користувач, вузол, пагінація."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ForbiddenError, UnauthorizedError
from app.models.devices import Node
from app.i18n import resolve_locale
from app.models.enums import Locale, NodeStatus
from app.models.users import User
from app.pagination import PageParams
from app.security import decode_access_token, hash_token
from app.services.certificates import node_certificate_valid

DbSession = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends()]

_bearer = HTTPBearer(auto_error=False, description="JWT доступу користувача")
_device_key = APIKeyHeader(
    name="X-Device-Token",
    auto_error=False,
    description="Токен пристрою, виданий під час введення вузла в експлуатацію",
)


def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Повертає користувача за JWT із заголовка Authorization.

    Мову профілю запам'ятовуємо в запиті, щоб нею відповідати на помилки.
    """
    if credentials is None:
        raise UnauthorizedError()
    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise UnauthorizedError("invalid_token")
    if user.blocked_at is not None:
        raise ForbiddenError("account_blocked")
    request.state.user_locale = user.locale
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_user_locale(request: Request, user: CurrentUser) -> Locale:
    """Мова відповіді: Accept-Language, інакше мова профілю користувача."""
    return resolve_locale(request.headers.get("accept-language"), user.locale)


UserLocale = Annotated[Locale, Depends(get_user_locale)]


def get_platform_admin(user: CurrentUser) -> User:
    """Дозволяє доступ лише адміністратору платформи."""
    if not user.is_platform_admin:
        raise ForbiddenError()
    return user


AdminUser = Annotated[User, Depends(get_platform_admin)]


def get_device_node(
    db: DbSession, token: Annotated[str | None, Depends(_device_key)]
) -> Node:
    """Автентифікує IoT-вузол за токеном пристрою (у БД лише його хеш)."""
    if not token:
        raise UnauthorizedError("device_unauthorized")
    node = db.scalar(select(Node).where(Node.device_token_hash == hash_token(token)))
    if node is None or node.status == NodeStatus.DISABLED:
        raise UnauthorizedError("device_unauthorized")
    if not node_certificate_valid(db, node.id, datetime.now(UTC)):
        raise UnauthorizedError("certificate_invalid")
    return node


DeviceNode = Annotated[Node, Depends(get_device_node)]
