from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.mcp.server import create_mcp_server
from app.services.auth_service import AuthService
from app.services.payment_service import PaymentService


client = TestClient(app)
payments = PaymentService()


def create_tenant() -> tuple[dict[str, str], object]:
    suffix = uuid4().hex[:12]
    response = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"Payments {suffix}", "organization_slug": f"payments-{suffix}"},
    )
    assert response.status_code == 201
    api_key = response.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        organization = AuthService().organization_for_key(db, api_key)
        db.expunge(organization)
        return {"X-API-Key": api_key}, organization
    finally:
        db.close()


def connect_source(headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/commerce-sources",
        headers=headers,
        json={"name": "Payments source", "source": "payments-provider", "store_url": "https://payments.example.com"},
    )
    assert response.status_code == 200
    return response.json()


def ingest(headers: dict[str, str], storefront_id: int, event_name: str, **payload_fields) -> dict:
    response = client.post(
        f"/api/analytics/sources/{storefront_id}/events",
        headers=headers,
        json={"event_name": event_name, "payload": {"order_id": "order-1", "currency": "USD", **payload_fields}},
    )
    assert response.status_code == 200, response.text
    return response.json()


def land_failed_payment_scenario(headers: dict[str, str], storefront_id: int, customer_id: str) -> None:
    ingest(headers, storefront_id, "purchase", revenue=100.0, customer_id=customer_id)
    ingest(
        headers,
        storefront_id,
        "payment_failed",
        revenue=100.0,
        customer_id=customer_id,
        metadata={"failure_code": "card_declined", "failure_reason": "insufficient funds"},
    )


def test_payment_lifecycle_lands_normalized_model() -> None:
    headers, organization = create_tenant()
    source = connect_source(headers)
    customer_id = f"customer-{uuid4().hex[:8]}"
    land_failed_payment_scenario(headers, source["id"], customer_id)
    ingest(headers, source["id"], "recovery_attempted", revenue=100.0, customer_id=customer_id)
    ingest(headers, source["id"], "recovery_succeeded", revenue=100.0, customer_id=customer_id)

    db = SessionLocal()
    try:
        metrics = payments.payment_metrics(db, organization)
        assert metrics.attempted == 1
        assert metrics.failed == 1
        assert metrics.failed_amount == 100.0
        assert metrics.success_rate == 0.0

        failures = payments.payment_failures(db, organization)
        assert len(failures) == 1
        assert failures[0].failure_code == "card_declined"
        assert failures[0].failure_reason == "insufficient funds"
        assert failures[0].customer_id == customer_id

        at_risk = payments.revenue_at_risk(db, organization)
        assert at_risk.open_amount == 0.0
        assert at_risk.open_cases == 0
        assert at_risk.recovered_amount == 100.0
        assert at_risk.recovered_cases == 1

        recovery = payments.payment_recovery(db, organization)
        assert recovery.attempted == 2
        assert recovery.succeeded == 1
        assert recovery.recovered_amount == 100.0
        assert recovery.revenue_at_risk == 0.0

        lifecycle = payments.transaction_lifecycle(db, organization, "order-1")
        kinds = [entry.kind for entry in lifecycle]
        assert kinds.count("order") == 1
        assert "payment_attempt" in kinds
        assert kinds.count("recovery_attempt") == 2

        history = payments.customer_payment_history(db, organization, customer_id)
        assert len(history) == len(lifecycle)
    finally:
        db.close()


def test_payment_landing_is_idempotent_for_duplicate_events() -> None:
    headers, organization = create_tenant()
    source = connect_source(headers)
    payload = {
        "order_id": "order-dup",
        "revenue": 50.0,
        "idempotency_key": "evt-dup-1",
        "metadata": {"failure_code": "card_declined"},
    }
    first = ingest(headers, source["id"], "payment_failed", **payload)
    second = ingest(headers, source["id"], "payment_failed", **payload)
    assert first["id"] == second["id"]

    db = SessionLocal()
    try:
        assert len(payments.payment_failures(db, organization)) == 1
        at_risk = payments.revenue_at_risk(db, organization)
        assert at_risk.open_cases == 1
        assert at_risk.open_amount == 50.0
    finally:
        db.close()


def test_successful_payment_closes_open_recovery_case() -> None:
    headers, organization = create_tenant()
    source = connect_source(headers)
    customer_id = f"customer-{uuid4().hex[:8]}"
    land_failed_payment_scenario(headers, source["id"], customer_id)
    ingest(headers, source["id"], "payment_succeeded", revenue=100.0, customer_id=customer_id)

    db = SessionLocal()
    try:
        at_risk = payments.revenue_at_risk(db, organization)
        assert at_risk.open_amount == 0.0
        assert at_risk.recovered_amount == 100.0

        metrics = payments.payment_metrics(db, organization)
        assert metrics.attempted == 2
        assert metrics.succeeded == 1
        assert metrics.failed == 1
        assert metrics.success_rate == 0.5
        assert metrics.succeeded_amount == 100.0
    finally:
        db.close()


def test_refunds_and_chargebacks_reduce_net_revenue() -> None:
    headers, organization = create_tenant()
    source = connect_source(headers)
    customer_id = f"customer-{uuid4().hex[:8]}"
    ingest(headers, source["id"], "purchase", revenue=100.0, customer_id=customer_id)
    ingest(headers, source["id"], "refund_created", revenue=30.0, customer_id=customer_id, metadata={"reason": "returned"})
    ingest(headers, source["id"], "chargeback_created", revenue=100.0, customer_id=customer_id)

    db = SessionLocal()
    try:
        revenue = payments.revenue_metrics(db, organization)
        assert revenue.gross == 100.0
        assert revenue.refunds == 30.0
        assert revenue.chargebacks == 100.0
        assert revenue.net == -30.0

        orders = payments.order_metrics(db, organization)
        assert orders.orders == 1
        assert orders.revenue == 100.0

        lifecycle = payments.transaction_lifecycle(db, organization, "order-1")
        kinds = {entry.kind for entry in lifecycle}
        assert {"order", "refund", "chargeback"} <= kinds
    finally:
        db.close()


def test_payment_data_is_isolated_between_tenants() -> None:
    first_headers, first_organization = create_tenant()
    second_headers, second_organization = create_tenant()
    source = connect_source(first_headers)
    customer_id = f"customer-{uuid4().hex[:8]}"
    land_failed_payment_scenario(first_headers, source["id"], customer_id)

    db = SessionLocal()
    try:
        metrics = payments.payment_metrics(db, second_organization)
        assert metrics.attempted == 0
        assert payments.payment_failures(db, second_organization) == []
        assert payments.revenue_at_risk(db, second_organization).open_cases == 0
        assert payments.customer_payment_history(db, second_organization, customer_id) == []
        assert payments.transaction_lifecycle(db, second_organization, "order-1") == []

        assert payments.transaction_lifecycle(db, first_organization, "order-1")
    finally:
        db.close()


def test_mcp_payment_tools_use_normalized_model() -> None:
    _, organization = create_tenant()
    server = create_mcp_server(organization)
    connected = server.call_tool(
        "register_commerce_source",
        {"name": "MCP payments", "source": "custom-payments", "store_url": "https://mcp-payments.example.com"},
    )
    storefront_id = connected["id"]
    customer_id = f"customer-{uuid4().hex[:8]}"
    server.call_tool(
        "ingest_canonical_commerce_event",
        {
            "storefront_id": storefront_id,
            "event_name": "purchase",
            "payload": {"order_id": "mcp-order-1", "revenue": 80, "currency": "USD", "customer_id": customer_id},
        },
    )
    server.call_tool(
        "ingest_canonical_commerce_event",
        {
            "storefront_id": storefront_id,
            "event_name": "payment_failed",
            "payload": {
                "order_id": "mcp-order-1",
                "revenue": 80,
                "currency": "USD",
                "customer_id": customer_id,
                "metadata": {"failure_code": "expired_card"},
            },
        },
    )
    server.call_tool(
        "ingest_canonical_commerce_event",
        {
            "storefront_id": storefront_id,
            "event_name": "recovery_succeeded",
            "payload": {"order_id": "mcp-order-1", "revenue": 80, "currency": "USD", "customer_id": customer_id},
        },
    )

    metrics = server.call_tool("get_payment_metrics")
    assert metrics["failed"] == 1
    assert metrics["failed_amount"] == 80.0

    failures = server.call_tool("get_payment_failures")
    assert failures["failures"][0]["failure_code"] == "expired_card"

    recovery = server.call_tool("get_payment_recovery")
    assert recovery["recovered_amount"] == 80.0

    at_risk = server.call_tool("get_revenue_at_risk")
    assert at_risk["recovered_cases"] == 1
    assert at_risk["open_cases"] == 0

    history = server.call_tool("get_customer_payment_history", {"customer_id": customer_id})
    kinds = {entry["kind"] for entry in history["history"]}
    assert {"order", "payment_attempt", "recovery_attempt"} <= kinds

    lifecycle = server.call_tool("get_transaction_lifecycle", {"order_id": "mcp-order-1"})
    assert len(lifecycle["events"]) == len(history["history"])

    revenue = server.call_tool("get_revenue_metrics")
    assert revenue["gross"] == 80.0

    orders = server.call_tool("get_order_metrics")
    assert orders["orders"] == 1
    assert orders["revenue"] == 80.0
