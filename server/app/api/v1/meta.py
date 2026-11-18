"""Довідкові маршрути без автентифікації: мови та відомості про дані."""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Header

from app.deps import DbSession
from app.i18n import parse_accept_language
from app.l10n import LOCALES
from app.privacy import CATEGORIES, RIGHTS
from app.services.admin import list_tariffs

router = APIRouter(tags=["service"])

AcceptLanguage = Annotated[str | None, Header()]


@router.get("/locales")
def locales() -> list[dict[str, Any]]:
    """Мови: код, назва, напрям тексту (ltr/rtl), чи підтримується інтерфейсом."""
    return [asdict(locale) for locale in LOCALES]


@router.get("/privacy")
def privacy(db: DbSession, accept_language: AcceptLanguage = None) -> dict[str, Any]:
    """Які персональні дані обробляються, навіщо, як довго, які права є."""
    locale = parse_accept_language(accept_language)
    return {
        "locale": locale.value,
        "categories": [asdict(item) for item in CATEGORIES[locale]],
        "rights": [asdict(item) for item in RIGHTS[locale]],
        "retention_by_tariff": [
            {"tariff": plan.code, "archive_days": plan.archive_days}
            for plan in list_tariffs(db)
        ],
    }
