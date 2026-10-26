from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends

from app.booking import service as booking_service
from app.identity.deps import require_admin
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
