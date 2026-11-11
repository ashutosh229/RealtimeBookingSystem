import asyncpg
from fastapi import APIRouter, Depends, Query, Response

from app.identity.deps import current_user
from app.notifications.schemas import NotificationList
from app.platform.db import get_conn
from app.platform.errors import ApiError

router = APIRouter(tags=["notifications"])


@router.get("/users/me/notifications", response_model=NotificationList)
async def list_notifications(
    since: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    """Poll with `since` = the highest id already seen. Results ascend by id."""
    rows = await conn.fetch(
        "SELECT id, type, payload, read_at, created_at FROM notifications"
        " WHERE user_id = $1 AND id > $2 ORDER BY id LIMIT $3",
        user["user_id"],
        since,
        limit,
    )
    return {"items": [dict(r) for r in rows]}


@router.post("/users/me/notifications/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: int,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    done = await conn.fetchval(
        "UPDATE notifications SET read_at = COALESCE(read_at, now())"
        " WHERE id = $1 AND user_id = $2 RETURNING id",
        notification_id,
        user["user_id"],
    )
    if done is None:
        raise ApiError(404, "NOT_FOUND", "Notification not found")  # also for other users' ids
    return Response(status_code=204)
