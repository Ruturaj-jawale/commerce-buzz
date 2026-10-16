"""MCP tools for Card Network, ATM, UPI Risk Assessment, and Cross-Rail Decline DNA."""

from datetime import date
from typing import Any

from app.db.database import SessionLocal
from app.db.models import Organization
from app.schemas.risk import RealTimeRiskEvaluationRequest
from app.services.risk_service import RiskAssessmentService


def _with_db(callback):
    db = SessionLocal()
    try:
        return callback(db)
    finally:
        db.close()


def _date_range(arguments: dict | None) -> tuple[date | None, date | None]:
    args = arguments or {}
    start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    return start_date, end_date


def create_risk_tools(organization: Organization) -> list[dict[str, Any]]:
    risk_service = RiskAssessmentService()

    def get_system_lens_handler(arguments: dict | None = None) -> dict[str, Any]:
        res = _with_db(lambda db: risk_service.detect_system_lens(db, organization))
        return res.model_dump(mode="json")

    def get_risk_assessment_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        start_date, end_date = _date_range(arguments)
        channel = args.get("channel")
        res = _with_db(
            lambda db: risk_service.calculate_risk_assessment(
                db, organization, start_date=start_date, end_date=end_date, channel=channel
            )
        )
        return res.model_dump(mode="json")

    def get_high_risk_entities_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        limit = min(max(int(args.get("limit", 20)), 1), 100)
        min_failures = max(int(args.get("min_failures", 1)), 0)
        channel = args.get("channel")
        res = _with_db(
            lambda db: risk_service.get_most_failed_entities(
                db, organization, limit=limit, min_failures=min_failures, channel=channel
            )
        )
        return {"entities": [item.model_dump(mode="json") for item in res]}

    def get_entity_risk_dna_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        entity_name = str(args.get("entity_name") or "").strip()
        if not entity_name:
            return {"error": "entity_name argument is required"}
        res = _with_db(
            lambda db: risk_service.get_entity_risk_dna(db, organization, entity_name)
        )
        return res.model_dump(mode="json")

    def evaluate_transaction_risk_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        req = RealTimeRiskEvaluationRequest(
            transaction_ref=str(args.get("transaction_ref") or "eval-txn"),
            entity_name=str(args.get("entity_name") or "Unknown Entity"),
            channel=args.get("channel", "CARD_SWIPE"),
            amount=float(args.get("amount", 10.0)),
            currency=str(args.get("currency", "USD")),
            card_bin=args.get("card_bin"),
            country_code=args.get("country_code"),
        )
        res = _with_db(
            lambda db: risk_service.evaluate_realtime_risk(db, organization, req)
        )
        return res.model_dump(mode="json")

    def ingest_statement_file_handler(arguments: dict | None = None) -> dict[str, Any]:
        from pathlib import Path
        from app.services.statement_ingestor import ingest_and_record_statement

        args = arguments or {}
        file_path = str(args.get("file_path") or "").strip()
        if not file_path:
            return {"error": "file_path argument is required"}
        path = Path(file_path)
        if not path.is_file():
            return {"error": f"File does not exist: {file_path}"}

        password = args.get("pdf_password")
        content = path.read_bytes()
        res = _with_db(
            lambda db: ingest_and_record_statement(
                db, organization, content, path.name, pdf_password=password
            )
        )
        return res.model_dump(mode="json")

    return [
        {
            "name": "get_system_lens",
            "description": "Auto-detects whether the organization operates primarily as Commerce Analytics (storefronts, orders, checkouts) or Bank/Card Network Switch (ATM, UPI, POS card swipe, interbank settlements).",
            "input_schema": {
                "type": "object",
                "properties": {},
            },
            "handler": get_system_lens_handler,
        },
        {
            "name": "get_risk_assessment",
            "description": "Returns systemic risk assessment, failure rates across ATM, UPI, Card Swipe, and ghost reversal metrics.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "ISO start date (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "ISO end date (YYYY-MM-DD)"},
                    "channel": {"type": "string", "enum": ["ATM", "CARD_SWIPE", "UPI", "ONLINE_CARD", "TRANSFER"]},
                },
            },
            "handler": get_risk_assessment_handler,
        },
        {
            "name": "get_high_risk_entities",
            "description": "Returns the leaderboard of entities, merchants, and ATMs ranked by most failed and returned transactions ('Most failed at which name').",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max entities to return (1-100)"},
                    "min_failures": {"type": "integer", "description": "Minimum failed transactions filter"},
                    "channel": {"type": "string", "enum": ["ATM", "CARD_SWIPE", "UPI", "ONLINE_CARD", "TRANSFER"]},
                },
            },
            "handler": get_high_risk_entities_handler,
        },
        {
            "name": "get_entity_risk_dna",
            "description": "Returns innovative Cross-Rail Decline DNA: multi-dimensional behavioral failure fingerprint and cross-rail commerce correlation.",
            "input_schema": {
                "type": "object",
                "required": ["entity_name"],
                "properties": {
                    "entity_name": {"type": "string", "description": "Merchant, ATM ID, or person name"},
                },
            },
            "handler": get_entity_risk_dna_handler,
        },
        {
            "name": "evaluate_transaction_risk",
            "description": "Real-Time Card Network Integration Middleware (Mastercard/Visa -> SaaS MCP -> Bank). Evaluates live transaction risk and returns APPROVE, REVIEW, or DECLINE decision.",
            "input_schema": {
                "type": "object",
                "required": ["transaction_ref", "entity_name", "amount"],
                "properties": {
                    "transaction_ref": {"type": "string", "description": "Transaction reference / auth request ID"},
                    "entity_name": {"type": "string", "description": "Merchant name or ATM terminal ID"},
                    "amount": {"type": "number", "description": "Transaction monetary amount"},
                    "channel": {"type": "string", "enum": ["ATM", "CARD_SWIPE", "UPI", "ONLINE_CARD", "TRANSFER"]},
                    "currency": {"type": "string", "description": "Currency code (default: USD)"},
                    "card_bin": {"type": "string", "description": "Card BIN (first 6-8 digits)"},
                    "country_code": {"type": "string", "description": "ISO country code"},
                },
            },
            "handler": evaluate_transaction_risk_handler,
        },
        {
            "name": "ingest_statement_file",
            "description": "Uploads and ingests a bank or card statement file (CSV, Excel, or PDF). Sanitizes PII/PCI, parses banking narrations, normalizes payments, and reconciles reversals automatically.",
            "input_schema": {
                "type": "object",
                "required": ["file_path"],
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the statement file (.csv, .xlsx, .xls, .pdf)"},
                    "pdf_password": {"type": "string", "description": "Optional password if the PDF is encrypted"},
                },
            },
            "handler": ingest_statement_file_handler,
        },
    ]
