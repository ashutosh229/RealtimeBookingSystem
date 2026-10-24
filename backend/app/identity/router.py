import asyncpg
from fastapi import APIRouter, Depends

from app.identity import service
from app.identity.deps import current_user
from app.identity.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.platform.db import get_conn

router = APIRouter()


@router.post("/auth/register", status_code=201, response_model=UserOut, tags=["auth"])
async def register(body: RegisterRequest, conn: asyncpg.Connection = Depends(get_conn)):
    return dict(await service.register(conn, body.email, body.name, body.password))


@router.post("/auth/login", response_model=TokenPair, tags=["auth"])
async def login(body: LoginRequest, conn: asyncpg.Connection = Depends(get_conn)):
    return await service.login(conn, body.email, body.password)


@router.post("/auth/refresh", response_model=TokenPair, tags=["auth"])
async def refresh(body: RefreshRequest, conn: asyncpg.Connection = Depends(get_conn)):
    return await service.refresh(conn, body.refresh_token)


@router.get("/users/me", response_model=UserOut, tags=["auth"])
async def me(user: dict = Depends(current_user)):
    return user
