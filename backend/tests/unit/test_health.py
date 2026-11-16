from fastapi.testclient import TestClient

from app.main import app


def test_healthz() -> None:
    r = TestClient(app).get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_instance_header_identifies_the_replica() -> None:
    assert TestClient(app).get("/healthz").headers["x-instance"]
