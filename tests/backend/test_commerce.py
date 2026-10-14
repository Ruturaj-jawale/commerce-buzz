from fastapi.testclient import TestClient
from uuid import uuid4

from app.db.database import SessionLocal
from app.main import app
from app.mcp.server import create_mcp_server
from app.services.auth_service import AuthService
from app.services.ingestion_job_service import IngestionJobService


client = TestClient(app)


def create_tenant() -> tuple[dict[str, str], object]:
    suffix = uuid4().hex[:12]
    response = client.post("/api/auth/bootstrap", json={"organization_name": f"Acme {suffix}", "organization_slug": f"acme-{suffix}"})
    assert response.status_code == 201
    api_key = response.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        organization = AuthService().organization_for_key(db, api_key)
        db.expunge(organization)
        return {"X-API-Key": api_key}, organization
    finally:
        db.close()


def test_any_commerce_source_feeds_first_party_analytics() -> None:
    headers, _ = create_tenant()
    warehouse = client.post(
        "/api/commerce-sources",
        headers=headers,
        json={
            "name": "Acme warehouse",
            "source": "commerce-warehouse",
            "store_url": "https://warehouse.example.com",
        },
    )
    assert warehouse.status_code == 200
    custom = client.post(
        "/api/commerce-sources",
        headers=headers,
        json={
            "name": "Acme custom source",
            "source": "custom-api",
            "store_url": "https://api.example.com",
        },
    )
    assert custom.status_code == 200

    warehouse_event = client.post(
        f"/api/analytics/sources/{warehouse.json()['id']}/events",
        headers=headers,
        json={"event_name": "purchase", "payload": {"order_id": "1001", "revenue": "20.50", "currency": "USD"}},
    )
    assert warehouse_event.status_code == 200
    assert warehouse_event.json()["event_name"] == "purchase"
    assert warehouse_event.json()["revenue"] == 20.5

    custom_event = client.post(
        f"/api/analytics/sources/{custom.json()['id']}/sample-purchase",
        headers=headers,
    )
    assert custom_event.status_code == 200
    assert custom_event.json()["source"] == "custom-api"

    summary = client.get("/api/analytics/summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["storefronts"] >= 2
    assert body["purchases"] >= 2
    assert body["revenue"] >= 20.5
    sources = {row["source"] for row in body["by_source"]}
    assert "commerce-warehouse" in sources
    assert "custom-api" in sources


def test_mcp_commerce_analytics_tools() -> None:
    _, organization = create_tenant()
    server = create_mcp_server(organization)
    connected = server.call_tool(
        "register_commerce_source",
        {
            "name": "MCP source",
            "source": "custom-commerce",
            "store_url": "https://mcp.example.com",
        },
    )
    ingested = server.call_tool(
        "ingest_canonical_commerce_event",
        {
            "storefront_id": connected["id"],
            "payload": {"order_id": "mcp-1", "revenue": 10, "currency": "USD"},
            "event_name": "purchase",
        },
    )
    assert ingested["revenue"] == 10
    summary = server.call_tool("get_analytics_summary")
    assert summary["events"] >= 1
    resource = server.read_resource("analytics://summary")
    assert "revenue" in resource


def test_tenants_cannot_read_or_write_each_others_commerce_data() -> None:
    first_headers, _ = create_tenant()
    second_headers, _ = create_tenant()
    source = client.post(
        "/api/commerce-sources",
        headers=first_headers,
        json={"name": "Private source", "source": "warehouse", "store_url": "https://private.example.com"},
    )
    assert source.status_code == 200
    assert client.get("/api/commerce-sources", headers=second_headers).json() == []
    denied = client.post(
        f"/api/analytics/sources/{source.json()['id']}/events",
        headers=second_headers,
        json={"event_name": "purchase", "payload": {"revenue": 10}},
    )
    assert denied.status_code == 404


def test_durable_ingestion_job_is_processed_by_worker_service() -> None:
    headers, _ = create_tenant()
    source = client.post(
        "/api/commerce-sources",
        headers=headers,
        json={"name": "Queued source", "source": "importer", "store_url": "https://importer.example.com"},
    )
    queued = client.post(
        f"/api/analytics/sources/{source.json()['id']}/ingestion-jobs",
        headers=headers,
        json={"event_name": "purchase", "payload": {"order_id": "job-order", "revenue": 99.0, "currency": "USD"}},
    )
    assert queued.status_code == 202
    assert queued.json()["status"] == "queued"

    db = SessionLocal()
    try:
        service = IngestionJobService()
        for _ in range(25):
            if not service.process_next(db):
                break
            status = client.get(f"/api/analytics/ingestion-jobs/{queued.json()['id']}", headers=headers).json()["status"]
            if status in {"completed", "failed"}:
                break
    finally:
        db.close()

    completed = client.get(f"/api/analytics/ingestion-jobs/{queued.json()['id']}", headers=headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["event_id"] is not None
