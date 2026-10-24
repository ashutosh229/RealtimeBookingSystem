import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.platform import db

PW = "password123"


def new_email() -> str:
    return f"{uuid.uuid4().hex[:12]}@itest.local"


@pytest_asyncio.fixture
async def client():
    try:
        await db.init_pool()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"database not reachable: {e}")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    async with db.get_pool().acquire() as conn:
        await conn.execute(
            "DELETE FROM refresh_tokens WHERE user_id IN"
            " (SELECT user_id FROM users WHERE email LIKE '%@itest.local')"
        )
        await conn.execute("DELETE FROM users WHERE email LIKE '%@itest.local'")
    await db.close_pool()


async def register(c, email=None, password=PW):
    email = email or new_email()
    r = await c.post("/v1/auth/register", json={"email": email, "name": "T", "password": password})
    return email, r


async def login(c, email, password=PW):
    return await c.post("/v1/auth/login", json={"email": email, "password": password})


async def test_register_returns_user_without_password(client):
    email, r = await register(client)
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == email and body["role"] == "student" and body["user_group"] == "general"
    assert "password" not in body and "password_hash" not in body


async def test_duplicate_email_is_case_insensitive(client):
    email, _ = await register(client)
    _, r = await register(client, email=email.upper())
    assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_TAKEN"


async def test_short_password_rejected(client):
    _, r = await register(client, password="short")
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_login_and_me(client):
    email, _ = await register(client)
    r = await login(client, email)
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["token_type"] == "bearer" and tokens["expires_in"] > 0
    me = await client.get(
        "/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200 and me.json()["email"] == email


async def test_wrong_password_and_unknown_email_look_identical(client):
    email, _ = await register(client)
    a = await login(client, email, "wrong-password")
    b = await login(client, new_email())
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["code"] == b.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert a.json()["error"]["message"] == b.json()["error"]["message"]


async def test_me_requires_token(client):
    r = await client.get("/v1/users/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    r = await client.get("/v1/users/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_refresh_rotates_and_old_token_is_dead(client):
    email, _ = await register(client)
    old = (await login(client, email)).json()["refresh_token"]
    r1 = await client.post("/v1/auth/refresh", json={"refresh_token": old})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != old
    r2 = await client.post("/v1/auth/refresh", json={"refresh_token": old})
    assert r2.status_code == 401


async def test_deactivated_user_is_locked_out(client):
    email, _ = await register(client)
    token = (await login(client, email)).json()["access_token"]
    async with db.get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET is_active = false WHERE email = $1", email)
    r = await client.get("/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert (await login(client, email)).status_code == 401


async def test_error_envelope_has_request_id(client):
    r = await client.get("/v1/users/me", headers={"X-Request-Id": "abc-123"})
    assert r.headers["X-Request-Id"] == "abc-123"
    assert r.json()["error"]["request_id"] == "abc-123"
