from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

from app.booking import repo, service
from app.booking.schemas import BookingCreate, BookingDetail, BookingOut, BookingPage, Status
from app.identity.deps import current_user
from app.platform.db import get_conn
from app.platform.errors import ApiError

router = APIRouter()


def _key(value: str | None) -> str:
    if not value:
        raise ApiError(400, "MALFORMED_REQUEST", "Idempotency-Key header is required")
    if not 8 <= len(value) <= 128:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key must be 8-128 characters")
    return value


def _respond(request: Request, r: service.Result) -> JSONResponse:
    headers: dict[str, str] = {}
    body = r.body
    if r.replayed:
        headers["Idempotent-Replay"] = "true"
    if r.status == 201:
        headers["Location"] = f"/v1/bookings/{body['booking_id']}"
    if r.status >= 400:  # stored error bodies carry no request_id; add this request's
        body = {"error": {**body["error"], "request_id": request.state.request_id}}
    return JSONResponse(body, status_code=r.status, headers=headers)


_DOC = {201: {"model": BookingOut}, 202: {"model": BookingOut}}


@router.post("/bookings", tags=["bookings"], responses=_DOC)
async def create_booking(
    body: BookingCreate,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return _respond(request, await service.create_booking(conn, user, body, _key(idempotency_key)))


@router.post("/waitlists", tags=["waitlists"], responses=_DOC)
async def join_waitlist(
    body: BookingCreate,
    request: Request,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    forced = body.model_copy(update={"waitlist_if_full": True})
    return _respond(
        request, await service.create_booking(conn, user, forced, _key(idempotency_key))
    )


@router.get("/bookings/{booking_id}", response_model=BookingDetail, tags=["bookings"])
async def get_booking(
    booking_id: UUID,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return await service.get_booking(conn, user, booking_id)


@router.post("/bookings/{booking_id}/cancel", response_model=BookingOut, tags=["bookings"])
async def cancel_booking(
    booking_id: UUID,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    return dict(await service.cancel_booking(conn, user, booking_id))


@router.get("/users/me/bookings", response_model=BookingPage, tags=["bookings"])
async def my_bookings(
    status: Status | None = None,
    from_: AwareDatetime | None = Query(None, alias="from"),
    to: AwareDatetime | None = None,
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = None,
    user: dict = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_conn),
):
    rows, nxt = await repo.list_for_user(
        conn,
        user["user_id"],
        status=status,
        frm=from_,
        to=to,
        limit=limit,
        cursor=cursor,
    )
    return {"items": [dict(r) for r in rows], "next_cursor": nxt}
