from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.database import SessionLocal
from app.main import app
from app.services.auth_service import AuthService


client = TestClient(app)


def create_user_tenant() -> tuple[str, str, dict]:
    suffix = uuid4().hex[:12]
    email = f"user-{suffix}@example.com"
    password = "correct-horse-battery"
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "organization_name": f"Acme {suffix}",
            "organization_slug": f"acme-{suffix}",
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201
    return email, password, {"X-API-Key": response.json()["api_key"]["key"]}


def login_cookie(email: str, password: str):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response


def test_rate_limit_returns_429_after_limit() -> None:
    limit = get_settings().rate_limit_per_minute
    headers = {"X-API-Key": f"ratelimit-test-{uuid4().hex}"}
    last_status = 200
    for _ in range(limit + 1):
        response = client.get("/api/auth/me", headers=headers)
        last_status = response.status_code
    assert last_status == 429


def test_login_sets_http_only_cookie_and_session_reaches_org_routes() -> None:
    email, password, _ = create_user_tenant()
    response = login_cookie(email, password)
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie
    assert "Secure" not in set_cookie  # development environment

    session_client = TestClient(app)
    session_client.cookies.update(client.cookies)
    me = session_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email
    assert "password_hash" not in me.text
    sources = session_client.get("/api/commerce-sources")
    assert sources.status_code == 200


def test_bearer_token_authorizes_api_clients_without_cookie() -> None:
    email, password, _ = create_user_tenant()
    token = login_cookie(email, password).json()["access_token"]
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == email


def test_logout_revokes_session_cookie_and_bearer_token() -> None:
    email, password, _ = create_user_tenant()
    token = login_cookie(email, password).json()["access_token"]
    session_client = TestClient(app)
    session_client.cookies.update(client.cookies)

    logout = session_client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert session_client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_session_missing_or_invalid_credentials_are_rejected() -> None:
    assert client.get("/api/auth/me").status_code == 401
    email, password, _ = create_user_tenant()
    bad = client.post("/api/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad.status_code == 401
    forged = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert forged.status_code == 401


def test_session_cannot_be_reassigned_to_another_tenant() -> None:
    email, password, _ = create_user_tenant()
    login_cookie(email, password)
    db = SessionLocal()
    try:
        user = AuthService().user_for_token(db, client.cookies.get("session"))
        other_suffix = uuid4().hex[:12]
        other = client.post(
            "/api/auth/bootstrap",
            json={"organization_name": f"Other {other_suffix}", "organization_slug": f"other-{other_suffix}"},
        )
        assert other.status_code == 201
        other_org_id = other.json()["organization"]["id"]
        tampered = create_access_token(user.id, other_org_id, user.token_version)
        response = client.get("/api/commerce-sources", headers={"Authorization": f"Bearer {tampered}"})
        assert response.status_code == 401
    finally:
        db.close()
