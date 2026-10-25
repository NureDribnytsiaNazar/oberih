"""Пагінація списків за параметрами limit/offset."""

from typing import Annotated, Any, TypeVar

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams:
    """Параметри сторінки зі строки запиту (?limit=20&offset=0)."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


def paginate(db: Session, stmt: Select[T], params: PageParams) -> tuple[list[T], int]:
    """Повертає записи поточної сторінки та загальну кількість записів."""
    count_stmt: Select[Any] = select(func.count()).select_from(
        stmt.order_by(None).subquery()
    )
    total = db.scalar(count_stmt) or 0
    items = db.scalars(stmt.limit(params.limit).offset(params.offset)).all()
    return list(items), total


def page_response(page: tuple[list[Any], int], params: PageParams) -> dict[str, Any]:
    """Тіло відповіді для схеми Page: записи, загальна кількість, межі."""
    items, total = page
    return {
        "items": items,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }
