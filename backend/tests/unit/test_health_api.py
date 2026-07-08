from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_envelope() -> None:
    client = TestClient(app)
    resp = client.get("/api/health")

    assert resp.status_code == 200
    body = resp.json()

    assert body["success"] is True
    assert body["message"] == ""
    assert isinstance(body["data"], dict)
    assert body["data"]["app"] == "istock"
    assert "version" in body["data"]
    assert "server_time" in body["data"]
