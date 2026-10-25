from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings
from tests.api.conftest import register


def test_register_starts_a_session_with_httponly_cookie(make_client):
    client = make_client()
    body = register(client, "New.User@Example.com")

    assert body["user"]["email"] == "new.user@example.com"
    set_cookie = client.post("/api/auth/login", json={"email": "new.user@example.com", "password": "correct-horse-battery"}).headers.get_list("set-cookie")
    access = next(c for c in set_cookie if c.startswith("access_token="))
    csrf = next(c for c in set_cookie if c.startswith("csrf_token="))
    assert "HttpOnly" in access and "SameSite=lax" in access and "Path=/api" in access
    assert "HttpOnly" not in csrf

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "new.user@example.com"
    assert "password" not in me.text


def test_duplicate_email_is_rejected_case_insensitively(make_client):
    register(make_client(), "sam@example.com")
    response = make_client().post("/api/auth/register", json={"email": "SAM@example.com", "password": "another-password"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_registration_input_is_validated(make_client):
    response = make_client().post("/api/auth/register", json={"email": "not-an-email", "password": "short"})
    assert response.status_code == 422
    fields = {d["field"] for d in response.json()["error"]["details"]}
    assert fields == {"email", "password"}


def test_wrong_password_and_unknown_email_get_the_same_answer(make_client):
    register(make_client(), "kim@example.com")
    client = make_client()
    wrong_password = client.post("/api/auth/login", json={"email": "kim@example.com", "password": "wrong-password"})
    unknown_email = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_protected_routes_require_a_session(make_client):
    client = make_client()
    for path in ("/api/auth/me", "/api/documents", "/api/conversations"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "not_authenticated"


def test_expired_and_forged_tokens_are_rejected(alice):
    me = alice.get("/api/auth/me").json()["user"]
    secret = get_settings().jwt_secret.get_secret_value()
    now = datetime.now(UTC)
    claims = {"sub": me["id"], "csrf": "x", "type": "access", "iat": now - timedelta(hours=2)}

    def use_token(token: str) -> None:
        alice.cookies.clear()  # replace the real session cookie instead of adding a second one
        # Python's cookie jar stores cookies for dot-less hosts such as "testserver" under ".local".
        alice.cookies.set("access_token", token, domain="testserver.local", path="/api")

    use_token(jwt.encode({**claims, "exp": now - timedelta(hours=1)}, secret))
    expired = alice.get("/api/auth/me")
    assert expired.status_code == 401
    assert "expired" in expired.json()["error"]["message"]

    use_token(jwt.encode({**claims, "exp": now + timedelta(hours=1)}, "a-different-secret-key-of-32-chars!!"))
    assert alice.get("/api/auth/me").status_code == 401

    use_token(jwt.encode({**claims, "exp": now + timedelta(hours=1)}, secret, algorithm="HS512"))
    assert alice.get("/api/auth/me").status_code == 401  # only HS256 is accepted


def test_state_changing_requests_need_the_csrf_header(alice):
    token = alice.headers.pop("X-CSRF-Token")
    assert alice.post("/api/conversations", json={}).status_code == 403

    alice.headers["X-CSRF-Token"] = "wrong-token"
    assert alice.post("/api/conversations", json={}).status_code == 403

    alice.headers["X-CSRF-Token"] = token
    assert alice.post("/api/conversations", json={}).status_code == 201


def test_logout_ends_the_session(alice):
    assert alice.post("/api/auth/logout").status_code == 204
    assert alice.get("/api/auth/me").status_code == 401


def test_login_attempts_are_rate_limited(make_client):
    client = make_client()
    statuses = [
        client.post("/api/auth/login", json={"email": "x@example.com", "password": "guess"}).status_code for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    limited = client.post("/api/auth/login", json={"email": "x@example.com", "password": "guess"})
    assert int(limited.headers["Retry-After"]) > 0
