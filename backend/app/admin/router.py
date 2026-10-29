from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.admin import metrics
from app.allocation import queries
from app.allocation.schemas import AllocationPage, MetricsSummaryOut, WaitlistPage
from app.booking import service as booking_service
from app.identity.deps import require_admin
from app.platform import clock
from app.platform.db import get_conn
from app.resources import service as resources_service
from app.resources.schemas import DeactivateBody, ResourceOut

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/resources/{resource_id}/deactivate", response_model=ResourceOut)
async def deactivate_resource(
    resource_id: UUID,
    body: DeactivateBody | None = None,
    admin: dict = Depends(require_admin),
    conn: asyncpg.Connection = Depends(get_conn),
):
    if body and body.force:
        return dict(await booking_service.force_deactivate(conn, admin, resource_id))
    return dict(await resources_service.deactivate(conn, resource_id))


@router.get("/waitlists", response_model=WaitlistPage, dependencies=[Depends(require_admin)])
async def admin_waitlists(
    resource_id: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    conn: asyncpg.Connection = Depends(get_conn),
):
    rows, nxt = await queries.list_active(conn, resource_id, limit, cursor)
    return {"items": [queries.entry_dict(r) for r in rows], "next_cursor": nxt}


@router.get("/allocations", response_model=AllocationPage, dependencies=[Depends(require_admin)])
async def admin_allocations(
    resource_id: UUID | None = None,
    from_: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    conn: asyncpg.Connection = Depends(get_conn),
):
    rows, nxt = await queries.list_allocations(conn, resource_id, from_, to, limit, cursor)
    return {"items": [dict(r) for r in rows], "next_cursor": nxt}


@router.get(
    "/metrics/summary",
    response_model=MetricsSummaryOut,
    dependencies=[Depends(require_admin)],
)
async def admin_metrics(
    resource_id: UUID | None = None,
    window_days: int = Query(14, ge=1, le=90),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await metrics.summary(
        conn, resource_id=resource_id, window_days=window_days, now=clock.now()
    )
