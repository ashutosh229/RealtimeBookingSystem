import time
from uuid import uuid4

import jwt
import pytest

from app.identity import security
from app.platform.config import get_settings
from app.platform.errors import ApiError


async def test_hash_and_verify():
    h = await security.hash_password("password123")
    assert h != "password123"
    assert await security.verify_password("password123", h)
    assert not await security.verify_password("wrong-password", h)


async def test_verify_rejects_garbage_hash():
    assert not await security.verify_password("x", "not-a-hash")


def test_access_token_roundtrip():
    uid = uuid4()
    claims = security.decode_access_token(security.create_access_token(uid, "student", "ug"))
    assert claims["sub"] == str(uid) and claims["role"] == "student" and claims["grp"] == "ug"


def _expect_401(token: str):
    with pytest.raises(ApiError) as ei:
        security.decode_access_token(token)
    assert ei.value.status == 401 and ei.value.code == "UNAUTHENTICATED"


def test_expired_token_rejected():
    _expect_401(
        jwt.encode(
            {"sub": "x", "exp": int(time.time()) - 10},
            get_settings().jwt_secret,
            algorithm="HS256",
        )
    )


def test_wrong_secret_rejected():
    _expect_401(
        jwt.encode(
            {"sub": "x", "exp": int(time.time()) + 60},
            "another-secret-another-secret-123456",
            algorithm="HS256",
        )
    )


def test_alg_none_rejected():
    _expect_401(jwt.encode({"sub": "x", "exp": int(time.time()) + 60}, None, algorithm="none"))


def test_refresh_tokens_are_unique_and_hash_matches():
    (r1, h1), (r2, _) = security.new_refresh_token(), security.new_refresh_token()
    assert r1 != r2 and security.hash_refresh(r1) == h1 and r1 != h1
