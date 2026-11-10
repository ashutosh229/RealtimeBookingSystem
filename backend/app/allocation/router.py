from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query

from app.allocation import chance, queries
from app.allocation.schemas import MyChanceOut, WaitlistEntryOut
from app.identity.deps import current_user
from app.platform import clock
from app.platform.db import get_conn
from app.platform.errors import ApiError

router = APIRouter(prefix="/waitlists", tags=["waitlists"])

me_router = APIRouter(tags=["users"])


@router.get("/{waitlist_id}", response_model=WaitlistEntryOut)
async def get_waitlist_entry(
    waitlist_id: UUID,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    row = await queries.get_entry(conn, waitlist_id)
    if row is None or (row["user_id"] != user["user_id"] and user["role"] != "admin"):
        raise ApiError(
            404, "NOT_FOUND", "Waitlist entry not found"
        )  # same answer whether it exists or not
    return queries.entry_dict(row)


@me_router.get("/users/me/chance", response_model=MyChanceOut)
async def my_chance(
    window_days: int = Query(14, ge=1, le=90),
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await chance.my_chance(conn, user["user_id"], window_days=window_days, now=clock.now())
