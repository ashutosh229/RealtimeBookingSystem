from datetime import date, datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

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
    eligible_only: bool = True,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    rows, nxt = await repo.list_page(
        conn,
        user=user,
        type=type,
        q=q,
        eligible_only=eligible_only,
        limit=limit,
        cursor=cursor,
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
    date: date | None = None,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    res = await _visible(conn, resource_id, user)
    return await availability.get_availability(conn, res, day=date, frm=from_, to=to)


@admin_router.post("", status_code=201, response_model=ResourceOut)
async def admin_create(body: ResourceCreate, conn: asyncpg.Connection = Depends(get_conn)):
    return dict(await service.create(conn, body))


@admin_router.patch("/{resource_id}", response_model=ResourceOut)
async def admin_update(
    resource_id: UUID,
    body: ResourceUpdate,
    conn: asyncpg.Connection = Depends(get_conn),
):
    return dict(await service.update(conn, resource_id, body))
