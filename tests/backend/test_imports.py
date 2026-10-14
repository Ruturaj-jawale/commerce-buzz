"""CSV/Excel import workflow: upload, mapping, validation, import, and isolation."""

import csv
import io
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.main import app
from app.services.auth_service import AuthService
from app.services.ingestion_job_service import IngestionJobService


client = TestClient(app)

HEADERS = ["Order #", "Date", "Email", "SKU", "Product", "Price", "Qty", "Total", "Currency", "Status"]
ROWS = [
    ["1001", "2026-09-15", "buyer@example.com", "SKU-A", "Running Shoe", "10.00", "2", "25.00", "USD", "Complete"],
    ["1001", "2026-09-15", "buyer@example.com", "SKU-B", "Socks", "5.00", "1", "25.00", "USD", "Complete"],
    ["1002", "2026-09-16", "buyer2@example.com", "SKU-C", "Hat", "30.00", "1", "30.00", "USD", "Complete"],
    ["1003", "2026-09-17", "buyer3@example.com", "SKU-D", "Broken", "xx", "1", "abc", "USD", "Complete"],
]

MAPPING = {
    "event_name": {"const": "purchase"},
    "order_id": {"column": "Order #"},
    "revenue": {"column": "Total"},
    "currency": {"column": "Currency"},
    "customer_id": {"column": "Email"},
    "occurred_at": {"column": "Date"},
    "items": {
        "product_id": {"column": "SKU"},
        "name": {"column": "Product"},
        "price": {"column": "Price"},
        "quantity": {"column": "Qty"},
    },
}


def create_tenant() -> tuple[dict[str, str], int]:
    suffix = uuid4().hex[:12]
    response = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"Import {suffix}", "organization_slug": f"import-{suffix}"},
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        organization = AuthService().organization_for_key(db, api_key)
        return {"X-API-Key": api_key}, organization.id
    finally:
        db.close()


def connect_source(headers: dict[str, str], provider: str = "godaddy-commerce") -> dict:
    response = client.post(
        "/api/commerce-sources",
        headers=headers,
        json={"name": "Import source", "source": provider, "store_url": "https://store.example.com"},
    )
    assert response.status_code == 200
    return response.json()


def csv_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def xlsx_bytes(headers: list[str], rows: list[list[str]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def upload(headers: dict[str, str], storefront_id: int, filename: str, content: bytes) -> object:
    return client.post(
        f"/api/imports/sources/{storefront_id}",
        headers=headers,
        files={"file": (filename, content, "application/octet-stream")},
    )


def upload_without_source(headers: dict[str, str], filename: str, content: bytes) -> object:
    return client.post(
        "/api/imports/file",
        headers=headers,
        data={"source_name": "Manual ledger", "source_label": "other"},
        files={"file": (filename, content, "application/octet-stream")},
    )


def drain() -> None:
    db = SessionLocal()
    try:
        service = IngestionJobService()
        for _ in range(50):
            if not service.process_next(db):
                break
    finally:
        db.close()


def test_upload_parses_csv_and_suggests_mapping() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    response = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))

    assert response.status_code == 201
    body = response.json()
    batch = body["batch"]
    assert batch["file_kind"] == "csv"
    assert batch["status"] == "uploaded"
    assert batch["total_rows"] == 4
    assert batch["columns"] == HEADERS
    assert body["sample_rows"][0]["Order #"] == "1001"

    suggested = body["suggested_mapping"]
    assert suggested["order_id"]["column"] == "Order #"
    assert suggested["revenue"]["column"] == "Total"
    assert suggested["currency"]["column"] == "Currency"
    assert suggested["customer_id"]["column"] == "Email"
    assert suggested["occurred_at"]["column"] == "Date"
    assert suggested["items"]["product_id"]["column"] == "SKU"
    assert suggested["items"]["name"]["column"] == "Product"
    assert suggested["items"]["price"]["column"] == "Price"
    assert suggested["items"]["quantity"]["column"] == "Qty"


def test_upload_can_create_a_generic_source_when_none_is_selected() -> None:
    headers, _ = create_tenant()
    response = upload_without_source(headers, "manual.csv", csv_bytes(HEADERS, ROWS))
    assert response.status_code == 201
    batch = response.json()["batch"]
    sources = client.get("/api/commerce-sources", headers=headers).json()
    assert batch["storefront_id"] == sources[0]["id"]
    assert sources[0]["name"] == "Manual ledger"
    assert sources[0]["source"] == "other"


def test_mapping_reports_counts_issues_and_previews() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    batch_id = created.json()["batch"]["id"]

    report = client.put(f"/api/imports/{batch_id}/mapping", headers=headers, json={"mapping": MAPPING})
    assert report.status_code == 200
    body = report.json()
    assert body["total_rows"] == 4
    assert body["valid_rows"] == 2
    assert body["invalid_rows"] == 1

    messages = [issue["message"] for issue in body["issues"]]
    assert any("revenue 'abc' is not a number" in message for message in messages)
    assert any("items.price 'xx' is not a number" in message for message in messages)
    assert all(issue["row"] == 4 for issue in body["issues"])

    previews = body["preview_payloads"]
    assert len(previews) == 2
    first = previews[0]
    assert first["event_name"] == "purchase"
    assert first["payload"]["order_id"] == "1001"
    assert first["payload"]["revenue"] == 25.0
    assert first["payload"]["customer_id"] == "buyer@example.com"
    assert first["payload"]["metadata"]["source_row"] == 1
    assert first["payload"]["items"] == [
        {"product_id": "SKU-A", "name": "Running Shoe", "price": 10.0, "quantity": 2},
        {"product_id": "SKU-B", "name": "Socks", "price": 5.0, "quantity": 1},
    ]

    status = client.get(f"/api/imports/{batch_id}", headers=headers)
    assert status.json()["batch"]["status"] == "validated"


def test_import_completes_and_is_idempotent_on_rerun() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    batch_id = created.json()["batch"]["id"]
    client.put(f"/api/imports/{batch_id}/mapping", headers=headers, json={"mapping": MAPPING})

    started = client.post(f"/api/imports/{batch_id}/import", headers=headers)
    assert started.status_code == 200
    assert started.json()["status"] == "importing"
    assert started.json()["queued_jobs"] == 2

    drain()
    final = client.get(f"/api/imports/{batch_id}", headers=headers).json()
    assert final["batch"]["status"] == "completed"
    assert final["batch"]["completed_jobs"] == 2
    assert final["batch"]["failed_jobs"] == 0
    assert final["job_errors"] == []

    summary = client.get("/api/analytics/summary", headers=headers).json()
    assert summary["purchases"] == 2
    assert summary["revenue"] == 55.0

    products = client.get("/api/analytics/top-products", headers=headers).json()
    top = {item["product_name"]: item for item in products}
    assert top["Running Shoe"]["units_sold"] == 2
    assert top["Hat"]["revenue"] == 30.0

    rerun = client.post(f"/api/imports/{batch_id}/import", headers=headers)
    assert rerun.status_code == 200
    drain()
    summary_after = client.get("/api/analytics/summary", headers=headers).json()
    assert summary_after["purchases"] == 2
    assert summary_after["revenue"] == 55.0


def test_xlsx_flat_import_maps_one_event_per_row() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    content = xlsx_bytes(
        ["OrderId", "Total", "Currency"],
        [["2001", "12.50", "USD"], ["2002", "7.25", "USD"]],
    )
    created = upload(headers, source["id"], "orders.xlsx", content)
    assert created.status_code == 201
    assert created.json()["batch"]["file_kind"] == "xlsx"
    batch_id = created.json()["batch"]["id"]

    mapping = {
        "event_name": {"const": "purchase"},
        "order_id": {"column": "OrderId"},
        "revenue": {"column": "Total"},
        "currency": {"column": "Currency"},
    }
    report = client.put(f"/api/imports/{batch_id}/mapping", headers=headers, json={"mapping": mapping})
    assert report.json()["valid_rows"] == 2

    client.post(f"/api/imports/{batch_id}/import", headers=headers)
    drain()
    final = client.get(f"/api/imports/{batch_id}", headers=headers).json()
    assert final["batch"]["status"] == "completed"
    assert final["batch"]["completed_jobs"] == 2

    summary = client.get("/api/analytics/summary", headers=headers).json()
    assert summary["purchases"] == 2
    assert summary["revenue"] == 19.75


def test_imports_are_isolated_between_tenants() -> None:
    first_headers, _ = create_tenant()
    second_headers, _ = create_tenant()
    source = connect_source(first_headers)
    created = upload(first_headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    batch_id = created.json()["batch"]["id"]

    assert client.get(f"/api/imports/{batch_id}", headers=second_headers).status_code == 404
    assert client.put(f"/api/imports/{batch_id}/mapping", headers=second_headers, json={"mapping": MAPPING}).status_code == 404
    assert client.post(f"/api/imports/{batch_id}/import", headers=second_headers).status_code == 404
    foreign_upload = upload(second_headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    assert foreign_upload.status_code == 404

    listed = client.get("/api/imports", headers=second_headers)
    assert listed.status_code == 200
    assert listed.json() == []
    mine = client.get("/api/imports", headers=first_headers)
    assert [batch["id"] for batch in mine.json()] == [batch_id]


def test_upload_rejects_bad_files_and_unauthenticated_requests() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)

    assert upload(headers, source["id"], "orders.txt", b"Order #\n1\n").status_code == 422
    assert upload(headers, source["id"], "orders.csv", b"\xff\xfe\x00\x01").status_code == 422
    assert upload(headers, source["id"], "empty.csv", csv_bytes(HEADERS, [])).status_code == 422
    assert upload({"X-API-Key": "invalid"}, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS)).status_code == 401
    unauthenticated = client.post(
        f"/api/imports/sources/{source['id']}",
        files={"file": ("orders.csv", csv_bytes(HEADERS, ROWS), "text/csv")},
    )
    assert unauthenticated.status_code == 401


def test_oversized_file_is_rejected() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    settings = get_settings()
    original = settings.max_import_file_bytes
    settings.max_import_file_bytes = 1024
    try:
        response = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS * 500))
        assert response.status_code == 413
    finally:
        settings.max_import_file_bytes = original


def test_invalid_mappings_are_rejected_with_clear_errors() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    batch_id = created.json()["batch"]["id"]
    url = f"/api/imports/{batch_id}/mapping"

    cases = [
        {"bogus": {"column": "Total"}},
        {"order_id": {"column": "Does not exist"}},
        {"items": "not-an-object"},
        {"items": {"color": {"column": "SKU"}}},
        {"event_name": {"const": "not-a-canonical-event"}},
        {"event_name": {"const": "purchase", "column": "Status"}},
        {"order_id": "Order #"},
    ]
    for mapping in cases:
        response = client.put(url, headers=headers, json={"mapping": mapping})
        assert response.status_code == 422, mapping
        assert response.json()["detail"]


def test_import_before_mapping_is_rejected() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, ROWS))
    batch_id = created.json()["batch"]["id"]

    response = client.post(f"/api/imports/{batch_id}/import", headers=headers)
    assert response.status_code == 422
    assert client.get(f"/api/imports/{batch_id}", headers=headers).json()["batch"]["status"] == "uploaded"


def test_mapping_with_all_invalid_rows_cannot_be_imported() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, [ROWS[3]]))
    batch_id = created.json()["batch"]["id"]
    report = client.put(f"/api/imports/{batch_id}/mapping", headers=headers, json={"mapping": MAPPING})
    assert report.json()["valid_rows"] == 0

    response = client.post(f"/api/imports/{batch_id}/import", headers=headers)
    assert response.status_code == 422


def test_number_and_date_coercion_handles_common_formats() -> None:
    headers, _ = create_tenant()
    source = connect_source(headers)
    rows = [
        ["3001", "09/15/2026", "a@example.com", "SKU-X", "Widget", "$1,234.50", "1", "($1,234.50)", "USD", "Complete"],
        ["3002", "September 15, 2026", "b@example.com", "SKU-Y", "Gadget", "5", "2", "10.00", "USD", "Complete"],
    ]
    created = upload(headers, source["id"], "orders.csv", csv_bytes(HEADERS, rows))
    batch_id = created.json()["batch"]["id"]
    report = client.put(f"/api/imports/{batch_id}/mapping", headers=headers, json={"mapping": MAPPING})
    assert report.status_code == 200
    body = report.json()
    assert body["valid_rows"] == 2
    first = body["preview_payloads"][0]["payload"]
    assert first["revenue"] == -1234.5
    assert first["occurred_at"] == "2026-09-15T00:00:00"
    second = body["preview_payloads"][1]["payload"]
    assert second["occurred_at"] == "2026-09-15T00:00:00"
