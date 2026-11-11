from fastapi.testclient import TestClient

from app.main import app

HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,idempotency-key,content-type",
}


def test_preflight_allows_the_expo_web_origin():
    r = TestClient(app).options(
        "/v1/bookings", headers={"Origin": "http://localhost:8081", **HEADERS}
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:8081"
    assert "idempotency-key" in r.headers["access-control-allow-headers"].lower()


def test_unknown_origins_are_refused():
    r = TestClient(app).options(
        "/v1/bookings", headers={"Origin": "https://evil.example", **HEADERS}
    )
    assert "access-control-allow-origin" not in r.headers
