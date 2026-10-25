from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.identity.router import router as identity_router
from app.platform import db, errors
from app.platform.errors import ApiError
from app.resources.router import admin_router as resources_admin_router
from app.resources.router import router as resources_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.init_pool()
    yield
    await db.close_pool()


app = FastAPI(title="RealTime Booking System", version="0.1.0", lifespan=lifespan)
errors.install(app)
app.include_router(identity_router, prefix="/v1")
app.include_router(resources_router, prefix="/v1")
app.include_router(resources_admin_router, prefix="/v1")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    try:
        async with db.get_pool().acquire() as conn:
            await conn.fetchval("SELECT 1")
    except Exception:
        raise ApiError(503, "SERVICE_BUSY", "database unavailable") from None
    return {"status": "ready"}
