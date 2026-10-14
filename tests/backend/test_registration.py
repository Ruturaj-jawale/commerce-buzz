"""Self-service registration: organization + owner creation, session, and tenant isolation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _generous_rate_limit():
    settings = get_settings()
    previous = settings.rate_limit_per_minute
    settings.rate_limit_per_minute = 100_000
    yield
    settings.rate_limit_per_minute = previous


def register_tenant(name: str | None = None) -> dict:
    suffix = uuid4().hex[:12]
    response = client.post(
        "/api/auth/register",
        json={
            "organization_name": name or f"Signup {suffix}",
            "email": f"owner-{suffix}@example.com",
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_creates_organization_owner_and_session() -> None:
    body = register_tenant()
    assert body["organization"]["id"]
    assert body["organization"]["name"].startswith("Signup ")
    assert body["api_key"]["key"].startswith("samcp_")
    assert body["access_token"]
    assert "password" not in str(body).lower().replace("password_hash", "")

    assert client.cookies.get("session") == body["access_token"]

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["organization"]["id"] == body["organization"]["id"]
    assert "password_hash" not in me.text
    assert client.get("/api/commerce-sources").json() == []
    client.post("/api/auth/logout")


def test_registration_rejects_duplicate_email() -> None:
    body = register_tenant()
    response = client.post(
        "/api/auth/register",
        json={
            "organization_name": f"Duplicate {uuid4().hex[:8]}",
            "email": body["email"].upper(),
            "password": "correct-horse-battery",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Email is already in use"


def test_registration_derives_unique_slugs_from_organization_name() -> None:
    suffix = uuid4().hex[:8]
    name = f"Slug Test {suffix}"
    first = register_tenant(name)
    second = register_tenant(name)
    assert first["organization"]["slug"] == f"slug-test-{suffix}"
    assert second["organization"]["slug"] == f"slug-test-{suffix}-2"


@pytest.mark.parametrize(
    "payload",
    [
        {"organization_name": "X", "email": "a@b.com", "password": "correct-horse-battery"},
        {"organization_name": "Acme", "email": "not-an-email", "password": "correct-horse-battery"},
        {"organization_name": "Acme", "email": "a@b.com", "password": "short"},
        {"organization_name": "Acme", "email": "a@b.com"},
    ],
)
def test_registration_rejects_invalid_input(payload: dict) -> None:
    assert client.post("/api/auth/register", json=payload).status_code == 422


def test_registration_can_be_disabled_and_requires_bootstrap_token_then() -> None:
    settings = get_settings()
    token = f"bootstrap-{uuid4().hex}"
    previous_open, previous_token = settings.allow_registration, settings.bootstrap_token
    settings.allow_registration, settings.bootstrap_token = False, token
    try:
        payload = {
            "organization_name": f"Gated {uuid4().hex[:8]}",
            "email": f"gated-{uuid4().hex[:8]}@example.com",
            "password": "correct-horse-battery",
        }
        assert client.post("/api/auth/register", json=payload).status_code == 403
        allowed = client.post("/api/auth/register", json=payload, headers={"X-Bootstrap-Token": token})
        assert allowed.status_code == 201
    finally:
        settings.allow_registration, settings.bootstrap_token = previous_open, previous_token


def test_registered_tenants_cannot_see_each_other_data() -> None:
    first, second = register_tenant(), register_tenant()

    first_client = TestClient(app)
    assert first_client.post("/api/auth/login", json={"email": first["email"], "password": "correct-horse-battery"}).status_code == 200
    second_client = TestClient(app)
    assert second_client.post("/api/auth/login", json={"email": second["email"], "password": "correct-horse-battery"}).status_code == 200

    created = first_client.post(
        "/api/commerce-sources",
        json={"name": "Private store", "source": "shopify", "store_url": "https://first.example.com"},
    )
    assert created.status_code == 200
    storefront_id = created.json()["id"]

    assert [source["id"] for source in first_client.get("/api/commerce-sources").json()] == [storefront_id]
    assert second_client.get("/api/commerce-sources").json() == []
    assert second_client.get("/api/analytics/summary").json()["storefronts"] == 0
    assert (
        second_client.post(
            f"/api/analytics/sources/{storefront_id}/sample-purchase",
            headers={"X-API-Key": second["api_key"]["key"]},
        ).status_code
        == 404
    )
