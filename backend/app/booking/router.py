import asyncpg
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse

from app.booking import service
from app.booking.schemas import BookingCreate, BookingOut
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
