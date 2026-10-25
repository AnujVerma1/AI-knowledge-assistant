from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_health_is_public_and_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}
    assert response.headers["X-Request-ID"]


def test_unknown_route_uses_the_json_error_format():
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
