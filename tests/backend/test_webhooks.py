import hashlib
import hmac
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.ingestion_job_service import IngestionJobService


client = TestClient(app)
WEBHOOK_SECRET = "whsec-test-secret-1234"


def create_tenant() -> tuple[dict[str, str], int]:
    suffix = uuid4().hex[:12]
    response = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"Webhook {suffix}", "organization_slug": f"webhook-{suffix}"},
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        organization = AuthService().organization_for_key(db, api_key)
        return {"X-API-Key": api_key}, organization.id
    finally:
        db.close()


def connect_source(headers: dict[str, str], secret: str | None = WEBHOOK_SECRET) -> dict:
    payload = {
        "name": "Webhook source",
        "source": "webhook-provider",
        "store_url": "https://hooks.example.com",
    }
    if secret is not None:
        payload["webhook_secret"] = secret
    response = client.post("/api/commerce-sources", headers=headers, json=payload)
    assert response.status_code == 200
    return response.json()


def sign(body: bytes, secret: str = WEBHOOK_SECRET, prefix: bool = False) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}" if prefix else digest


def post_webhook(storefront_id: int, body: bytes, signature: str | None) -> object:
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Signature"] = signature
    return client.post(f"/api/webhooks/sources/{storefront_id}", content=body, headers=headers)


def event_body(**payload_fields) -> bytes:
    return json.dumps({"event_name": "purchase", "payload": payload_fields}, separators=(",", ":")).encode("utf-8")


def test_webhook_with_valid_signature_is_accepted_and_processed() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    body = event_body(order_id="wh-1", revenue="42.00", currency="USD")

    accepted = post_webhook(source["id"], body, sign(body))
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"

    db = SessionLocal()
    try:
        service = IngestionJobService()
        for _ in range(25):
            if not service.process_next(db):
                break
            status = client.get(f"/api/analytics/ingestion-jobs/{accepted.json()['id']}", headers=headers).json()["status"]
            if status in {"completed", "failed"}:
                break
    finally:
        db.close()

    job = client.get(f"/api/analytics/ingestion-jobs/{accepted.json()['id']}", headers=headers)
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    summary = client.get("/api/analytics/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["revenue"] >= 42.0


def test_webhook_accepts_prefixed_sha256_signature() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    body = event_body(order_id="wh-2", revenue=10, currency="USD")
    accepted = post_webhook(source["id"], body, sign(body, prefix=True))
    assert accepted.status_code == 202


def test_webhook_rejects_invalid_and_missing_signatures() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    body = event_body(order_id="wh-3", revenue=10)

    invalid = post_webhook(source["id"], body, "0" * 64)
    assert invalid.status_code == 401

    missing = post_webhook(source["id"], body, None)
    assert missing.status_code == 401

    tampered_body = event_body(order_id="wh-3-tampered", revenue=10)
    wrong_body_signature = sign(tampered_body)
    assert post_webhook(source["id"], body, wrong_body_signature).status_code == 401


def test_webhook_unknown_source_or_unconfigured_secret_is_not_found() -> None:
    headers, _ = create_tenant()
    assert post_webhook(999999, event_body(order_id="x"), "0" * 64).status_code == 404

    no_secret_source = connect_source(headers, secret=None)
    body = event_body(order_id="wh-4", revenue=5)
    assert post_webhook(no_secret_source["id"], body, sign(body)).status_code == 404


def test_webhook_oversized_payload_is_rejected() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    limit = get_settings().max_ingestion_payload_bytes
    body = json.dumps(
        {"event_name": "purchase", "payload": {"pad": "x" * (limit + 1)}},
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(body) > limit
    response = post_webhook(source["id"], body, sign(body))
    assert response.status_code == 413


def test_webhook_job_is_not_visible_to_other_tenants() -> None:
    first_headers, _ = create_tenant()
    second_headers, _ = create_tenant()
    source = connect_source(first_headers)
    body = event_body(order_id="wh-5", revenue=7)
    accepted = post_webhook(source["id"], body, sign(body))
    assert accepted.status_code == 202
    denied = client.get(f"/api/analytics/ingestion-jobs/{accepted.json()['id']}", headers=second_headers)
    assert denied.status_code == 404
