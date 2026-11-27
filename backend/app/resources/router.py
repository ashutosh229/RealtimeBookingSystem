from datetime import date, datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, Response

from app.availability import cache as availability_cache
from app.availability import service as availability
from app.identity.deps import current_user, require_admin
from app.platform.db import get_conn
from app.platform.errors import ApiError
from app.resources import repo, service
from app.resources.schemas import (
    AvailabilityOut,
    ResourceCreate,
    ResourceOut,
    ResourcePage,
    ResourceType,
    ResourceUpdate,
)

router = APIRouter(prefix="/resources", tags=["resources"])
admin_router = APIRouter(
    prefix="/admin/resources", tags=["admin"], dependencies=[Depends(require_admin)]
)


async def _visible(conn: asyncpg.Connection, rid: UUID, user: dict) -> asyncpg.Record:
    res = await repo.get(conn, rid)
    if res is None or (not res["active"] and user["role"] != "admin"):
        raise ApiError(404, "NOT_FOUND", "Resource not found")
    return res


@router.get("", response_model=ResourcePage)
async def list_resources(
    type: ResourceType | None = None,
    q: str | None = Query(None, max_length=100),
    available_from: datetime | None = None,
    available_to: datetime | None = None,
    eligible_only: bool = True,
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_m: int | None = Query(None, ge=1, le=50000),
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    geo = (lat, lon, radius_m)
    if any(v is not None for v in geo) and not all(v is not None for v in geo):
        raise ApiError(422, "VALIDATION_ERROR", "lat, lon and radius_m must be given together")
    window = (available_from, available_to)
    if (available_from is None) != (available_to is None):
        raise ApiError(422, "VALIDATION_ERROR", "available_from and available_to go together")
    if available_from and available_to:
        if available_from.tzinfo is None or available_to.tzinfo is None:
            raise ApiError(422, "VALIDATION_ERROR", "times need a timezone offset")
        if available_to <= available_from:
            raise ApiError(422, "VALIDATION_ERROR", "available_to must be after available_from")
    rows, nxt = await repo.list_page(
        conn,
        user=user,
        type=type,
        q=q,
        eligible_only=eligible_only,
        limit=limit,
        cursor=cursor,
        near=(lat, lon, radius_m) if radius_m is not None else None,  # type: ignore[arg-type]
        free_between=window if available_from else None,  # type: ignore[arg-type]
    )
    return {"items": [dict(r) for r in rows], "next_cursor": nxt}


@router.get("/{resource_id}", response_model=ResourceOut)
async def get_resource(
    resource_id: UUID,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return dict(await _visible(conn, resource_id, user))


@router.get("/{resource_id}/availability", response_model=AvailabilityOut)
async def get_availability(
    resource_id: UUID,
    request: Request,
    response: Response,
    date: date | None = None,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    async def load():
        res = await _visible(
            conn, resource_id, user
        )  # 404 for unknown or (non-admin) inactive resources
        data = await availability.get_availability(conn, res, day=date, frm=from_, to=to)
        return data, bool(res["active"])  # only active resources are cached

    no_cache = "no-cache" in request.headers.get("cache-control", "").lower()
    if date is not None and from_ is None and to is None and not no_cache:
        data, state = await availability_cache.cached(str(resource_id), date.isoformat(), load)
    else:
        data, _ = await load()
        state = "BYPASS"
    response.headers["X-Cache"] = state
    return data


@admin_router.post("", status_code=201, response_model=ResourceOut)
async def admin_create(body: ResourceCreate, conn: asyncpg.Connection = Depends(get_conn)):
    return dict(await service.create(conn, body))


@admin_router.patch("/{resource_id}", response_model=ResourceOut)
async def admin_update(
    resource_id: UUID,
    body: ResourceUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
):
    out = dict(await service.update(conn, resource_id, body))
    await availability_cache.bump(resource_id)  # after commit: read-your-writes (ADR-0020)
    return out
