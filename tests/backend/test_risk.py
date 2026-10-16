"""Tests for Risk Assessment, Entity Failure Leaderboard, Real-Time Card Evaluation, and Decline DNA."""

from uuid import uuid4
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.db.models import Organization, Payment, Storefront
from app.integrations.storefronts.base import CanonicalCommerceEvent
from app.main import app
from app.mcp.server import create_mcp_server
from app.services.auth_service import AuthService
from app.services.payment_service import PaymentService

client = TestClient(app)


def _setup_test_environment():
    suffix = uuid4().hex[:12]
    res = client.post(
        "/api/auth/bootstrap",
        json={"organization_name": f"RiskCorp {suffix}", "organization_slug": f"riskcorp-{suffix}"},
    )
    assert res.status_code == 201
    api_key = res.json()["api_key"]["key"]
    headers = {"X-API-Key": api_key}

    db = SessionLocal()
    try:
        org = AuthService().organization_for_key(db, api_key)
        storefront = Storefront(
            organization_id=org.id,
            name="Bank Switch Feeds",
            provider="mastercard-switch",
            store_url="https://switch.example.com",
        )
        db.add(storefront)
        db.commit()
        db.refresh(storefront)

        # Ingest a dataset with various channels (ATM, UPI, POS, ECOM) and failed/returned entries
        service = PaymentService()

        # 1. Swiggy: 3 attempts, 2 failed/returned -> High Failure Rate
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="swiggy-tx-1",
                revenue=45.0,
                currency="USD",
                properties={"idempotency_key": f"sw-1-{suffix}", "narration": "UPI/50291823/SWIGGY/ICICI RRN 112233445566"},
            ),
        )
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="swiggy-tx-2",
                revenue=45.0,
                currency="USD",
                properties={"idempotency_key": f"sw-2-{suffix}", "narration": "REV-UPI SWIGGY FAILED TXN REFUND RRN 112233445566"},
            ),
        )
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="swiggy-tx-3",
                revenue=60.0,
                currency="USD",
                properties={"idempotency_key": f"sw-3-{suffix}", "narration": "UPI/99882211/SWIGGY/HDFC"},
            ),
        )

        # 2. SBI ATM: 2 attempts, 1 failed dispense
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="atm-tx-1",
                revenue=200.0,
                currency="USD",
                properties={"idempotency_key": f"atm-1-{suffix}", "narration": "ATM WDL CASH SBI KOTHUD PUNE RRN 778899001122"},
            ),
        )
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="atm-tx-2",
                revenue=200.0,
                currency="USD",
                properties={"idempotency_key": f"atm-2-{suffix}", "narration": "REVERSAL ATM WDL CASH SBI KOTHUD PUNE DISPENSE FAILED RRN 778899001122"},
            ),
        )

        # 3. Starbucks: 1 successful POS card swipe
        service.land_event(
            db, org, storefront,
            CanonicalCommerceEvent(
                event_name="purchase",
                order_id="starbucks-tx-1",
                revenue=15.0,
                currency="USD",
                properties={"idempotency_key": f"sb-1-{suffix}", "narration": "POS 401234xxxx STARBUCKS PUNE IN"},
            ),
        )
        db.commit()

        return headers, org.id
    finally:
        db.close()


def test_risk_assessment_api():
    headers, _ = _setup_test_environment()

    res = client.get("/api/analytics/risk-assessment", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["total_transactions"] >= 5
    assert data["failed_transactions"] >= 2
    assert data["returned_transactions"] >= 2
    assert data["overall_failure_rate"] > 0
    assert len(data["channel_breakdown"]) >= 2
    assert any(c["channel"] == "UPI" for c in data["channel_breakdown"])
    assert any(c["channel"] == "ATM" for c in data["channel_breakdown"])


def test_most_failed_entities_leaderboard():
    headers, _ = _setup_test_environment()

    # The user requirement: "find most fell transaction at which name"
    res = client.get("/api/analytics/risk-entities", headers=headers)
    assert res.status_code == 200
    entities = res.json()

    assert len(entities) >= 1
    top_entity = entities[0]
    assert top_entity["rank"] == 1
    assert top_entity["failed_count"] >= 1 or top_entity["returned_count"] >= 1
    assert top_entity["risk_score"] > 0
    assert top_entity["risk_tier"] in ["CRITICAL", "HIGH", "ELEVATED", "NORMAL"]
    assert len(top_entity["recommendation"]) > 5


def test_realtime_card_network_evaluation():
    headers, _ = _setup_test_environment()

    # Mastercard/Visa sends authorization request to our risk middleware
    payload = {
        "transaction_ref": "auth-req-999",
        "entity_name": "Swiggy",
        "channel": "UPI",
        "amount": 75.0,
        "currency": "USD",
        "country_code": "IND",
    }
    res = client.post("/api/risk/evaluate", headers=headers, json=payload)
    assert res.status_code == 200
    decision = res.json()

    assert decision["transaction_ref"] == "auth-req-999"
    assert decision["decision"] in ["APPROVE", "REVIEW", "DECLINE"]
    assert decision["risk_score"] >= 0
    assert len(decision["suggested_action"]) > 5
    assert len(decision["risk_factors"]) >= 1


def test_cross_rail_decline_dna():
    headers, _ = _setup_test_environment()

    res = client.get("/api/analytics/risk-dna/Swiggy", headers=headers)
    assert res.status_code == 200
    dna = res.json()

    assert dna["entity_name"] == "Swiggy"
    assert "channel_vulnerabilities" in dna
    assert "UPI" in dna["channel_vulnerabilities"]
    assert "reversal_velocity_cadence" in dna
    assert "strategic_remediation" in dna


def test_risk_mcp_tools():
    headers, org_id = _setup_test_environment()

    db = SessionLocal()
    try:
        org = db.get(Organization, org_id)
        server = create_mcp_server(org)

        # 1. Test get_risk_assessment tool
        tool_names = [t["name"] for t in server.list_tools()]
        assert "get_system_lens" in tool_names
        assert "get_risk_assessment" in tool_names
        assert "get_high_risk_entities" in tool_names
        assert "get_entity_risk_dna" in tool_names
        assert "evaluate_transaction_risk" in tool_names

        # 2. Call get_system_lens via MCP
        lens_res = server.call_tool("get_system_lens", {})
        assert lens_res["detected_mode"] in ["COMMERCE", "BANK_NETWORK", "HYBRID"]
        assert lens_res["recommended_lens"] in ["COMMERCE", "BANK_NETWORK"]
        assert "rationale" in lens_res

        # 3. Call get_risk_assessment via MCP
        risk_res = server.call_tool("get_risk_assessment", {})
        assert risk_res["total_transactions"] >= 5
        assert risk_res["overall_failure_rate"] > 0

        # 4. Call get_high_risk_entities via MCP
        entities_res = server.call_tool("get_high_risk_entities", {"limit": 5})
        assert "entities" in entities_res
        assert len(entities_res["entities"]) >= 1

        # 5. Call evaluate_transaction_risk via MCP
        eval_res = server.call_tool("evaluate_transaction_risk", {
            "transaction_ref": "mcp-auth-1",
            "entity_name": "SBI ATM",
            "channel": "ATM",
            "amount": 350.0,
        })
        assert eval_res["decision"] in ["APPROVE", "REVIEW", "DECLINE"]
    finally:
        db.close()


def test_system_lens_detection():
    headers, org_id = _setup_test_environment()

    res = client.get("/api/analytics/system-lens", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["detected_mode"] in ["COMMERCE", "BANK_NETWORK", "HYBRID"]
    assert data["confidence_score"] >= 0.5
    assert data["recommended_lens"] in ["COMMERCE", "BANK_NETWORK"]
    assert len(data["rationale"]) > 5
    assert data["total_bank_transactions"] >= 3
    assert "active_banking_rails" in data

