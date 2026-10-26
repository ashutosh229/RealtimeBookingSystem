from collections.abc import Mapping
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg

from app.platform.errors import ApiError
from app.resources import repo
from app.resources.schemas import ResourceCreate, ResourceUpdate

_UPDATABLE = {
    "name",
    "capacity",
    "open_time",
    "close_time",
    "max_slots_per_booking",
    "max_quantity_per_booking",
    "policy_name",
    "lat",
    "lon",
}


def validate_config(cfg: Mapping) -> None:
    def bad(msg: str):
        raise ApiError(422, "VALIDATION_ERROR", msg)

    if cfg["type"] == "SEAT" and cfg["capacity"] != 1:
        bad("a SEAT must have capacity 1")
    if cfg["type"] == "SEAT" and cfg["max_quantity_per_booking"] != 1:
        bad("a SEAT must have max_quantity_per_booking 1")
    if cfg["max_quantity_per_booking"] > cfg["capacity"]:
        bad("max_quantity_per_booking cannot exceed capacity")
    if cfg["open_time"] >= cfg["close_time"]:
        bad("open_time must be before close_time")
    try:
        ZoneInfo(cfg["timezone"])
    except (ZoneInfoNotFoundError, ValueError, OSError):
        bad("unknown IANA timezone")
    if (cfg.get("lat") is None) != (cfg.get("lon") is None):
        bad("lat and lon must be given together")


async def create(conn: asyncpg.Connection, body: ResourceCreate) -> asyncpg.Record:
    cfg = body.model_dump()
    validate_config(cfg)
    async with conn.transaction():
        rid = await conn.fetchval(
            "INSERT INTO resources (type, name, capacity, slot_minutes, open_time, close_time, timezone,"
            " max_slots_per_booking, max_quantity_per_booking, policy_name, lat, lon)"
            " VALUES ($1::resource_type, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING resource_id",
            cfg["type"],
            cfg["name"],
            cfg["capacity"],
            cfg["slot_minutes"],
            cfg["open_time"],
            cfg["close_time"],
            cfg["timezone"],
            cfg["max_slots_per_booking"],
            cfg["max_quantity_per_booking"],
            cfg["policy_name"],
            cfg["lat"],
            cfg["lon"],
        )
        for g in set(cfg["eligible_groups"]):
            await conn.execute("INSERT INTO resource_eligibility VALUES ($1, $2)", rid, g)
    return await repo.get(conn, rid)


async def update(conn: asyncpg.Connection, rid: UUID, body: ResourceUpdate) -> asyncpg.Record:
    changes = body.model_dump(exclude_unset=True)
    try:
        async with conn.transaction():
            cur = await repo.get_for_update(
                conn, rid
            )  # booking path will take FOR SHARE on this row
            if cur is None:
                raise ApiError(404, "NOT_FOUND", "Resource not found")
            validate_config(
                {
                    **dict(cur),
                    **{k: v for k, v in changes.items() if k != "eligible_groups"},
                }
            )
            if "capacity" in changes:
                used = await conn.fetchval(
                    "SELECT COALESCE(MAX(used), 0) FROM slot_usage WHERE resource_id = $1 AND slot_start >= now()",
                    rid,
                )
                if changes["capacity"] < used:
                    raise ApiError(
                        409,
                        "CAPACITY_UNAVAILABLE",
                        f"capacity cannot go below already-booked usage ({used})",
                    )
                await conn.execute(
                    "UPDATE slot_usage SET capacity = $2 WHERE resource_id = $1 AND slot_start >= now()",
                    rid,
                    changes["capacity"],
                )
            sets, args = [], [rid]
            for k, v in changes.items():
                if k in _UPDATABLE:
                    args.append(v)
                    sets.append(f"{k} = ${len(args)}")
            if sets:
                await conn.execute(
                    f"UPDATE resources SET {', '.join(sets)}, version = version + 1 WHERE resource_id = $1",
                    *args,
                )
            if changes.get("eligible_groups") is not None:
                await conn.execute("DELETE FROM resource_eligibility WHERE resource_id = $1", rid)
                for g in set(changes["eligible_groups"]):
                    await conn.execute("INSERT INTO resource_eligibility VALUES ($1, $2)", rid, g)
    except asyncpg.CheckViolationError:  # a concurrent booking raised usage past the new capacity
        raise ApiError(
            409, "CAPACITY_UNAVAILABLE", "capacity changed concurrently; retry"
        ) from None
    return await repo.get(conn, rid)


async def deactivate(conn: asyncpg.Connection, rid: UUID) -> asyncpg.Record:
    async with conn.transaction():
        cur = await repo.get_for_update(conn, rid)
        if cur is None:
            raise ApiError(404, "NOT_FOUND", "Resource not found")
        n = await conn.fetchval(
            "SELECT count(*) FROM bookings WHERE resource_id = $1"
            " AND status IN ('CONFIRMED','WAITLISTED') AND end_time > now()",
            rid,
        )
        if n:
            raise ApiError(
                409,
                "HAS_ACTIVE_BOOKINGS",
                "Resource has active future bookings",
                {"count": n},
            )
        await conn.execute(
            "UPDATE resources SET active = false, version = version + 1 WHERE resource_id = $1",
            rid,
        )
    return await repo.get(conn, rid)
