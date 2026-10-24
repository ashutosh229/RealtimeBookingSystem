import asyncio
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.platform.config import get_settings
from app.platform.errors import ApiError

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password-for-constant-time-checks")


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_ph.hash, password)  # CPU-bound: keep off the event loop


async def verify_password(password: str, hashed: str) -> bool:
    try:
        return await asyncio.to_thread(_ph.verify, hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


async def verify_dummy(password: str) -> None:
    """Burn the same time as a real check so unknown emails are not detectable by timing."""
    await verify_password(password, _DUMMY_HASH)


def create_access_token(user_id: UUID, role: str, group: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "grp": group,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_ttl_minutes),
    }
    return jwt.encode(claims, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as e:
        raise ApiError(401, "UNAUTHENTICATED", "Invalid or expired token") from e


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_refresh_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh(raw)
