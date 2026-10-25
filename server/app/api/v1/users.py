"""Маршрути профілю поточного користувача."""

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.users import DeleteAccountRequest, UserExport, UserOut, UserUpdate
from app.services import users as users_service

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=UserOut)
def get_me(user: CurrentUser) -> object:
    """Профіль поточного користувача."""
    return user


@router.patch("", response_model=UserOut)
def update_me(data: UserUpdate, user: CurrentUser, db: DbSession) -> object:
    """Зміна імені, мови, часового поясу, системи мір."""
    return users_service.update_profile(db, user, data)


@router.get("/export")
def export_me(user: CurrentUser, db: DbSession) -> UserExport:
    """Експорт усіх персональних даних (право на доступ, GDPR)."""
    return users_service.export_data(db, user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(data: DeleteAccountRequest, user: CurrentUser, db: DbSession) -> None:
    """Видалення облікового запису: знеособлення з підтвердженням паролем."""
    users_service.anonymize(db, user, data.password)
