"""Маршрути постановки на охорону, зняття з охорони та журналу дій."""

import uuid

from fastapi import APIRouter, Request

from app.deps import CurrentUser, DbSession, Paging
from app.models.facilities import Facility
from app.pagination import page_response
from app.schemas.common import Page
from app.schemas.events import (
    ArmingLogOut,
    ArmRequest,
    DisarmRequest,
    FacilityStateOut,
)
from app.services import arming as service
from app.services.access import Permission, require_access

router = APIRouter(prefix="/facilities/{facility_id}", tags=["arming"])


def _state(facility: Facility) -> FacilityStateOut:
    return FacilityStateOut(
        facility_id=facility.id,
        mode=facility.mode,
        mode_changed_at=facility.mode_changed_at,
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/arm")
def arm(
    facility_id: uuid.UUID,
    data: ArmRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FacilityStateOut:
    """Постановка на охорону: away — повна (із затримкою виходу), home — «Вдома»."""
    facility, _ = require_access(db, facility_id, user, Permission.ARM)
    service.arm(db, facility, user, data.mode, data.source, _client_ip(request))
    return _state(facility)


@router.post("/disarm")
def disarm(
    facility_id: uuid.UUID,
    data: DisarmRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FacilityStateOut:
    """Зняття з охорони; потрібне повторне підтвердження паролем або TOTP."""
    facility, member = require_access(db, facility_id, user, Permission.ARM)
    service.disarm(db, facility, member, user, data, _client_ip(request))
    return _state(facility)


@router.get("/arming-log", response_model=Page[ArmingLogOut])
def arming_log(
    facility_id: uuid.UUID, user: CurrentUser, db: DbSession, paging: Paging
) -> object:
    """Журнал постановки та зняття з охорони (хто, коли, звідки)."""
    facility, _ = require_access(db, facility_id, user, Permission.VIEW_EVENTS)
    return page_response(service.list_log(db, facility, paging), paging)
