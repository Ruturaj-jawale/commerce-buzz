"""MCP tools for the universal payment and revenue-recovery contract.

Provider-neutral: adapters translate provider payloads at ingestion; these
tools only read the normalized model. No provider-specific tools.
"""

from datetime import date
from typing import Any

from app.db.database import SessionLocal
from app.db.models import Organization
from app.services.payment_service import PaymentService


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


def create_payment_tools(organization: Organization) -> list[dict[str, Any]]:
    payments = PaymentService()

    def get_payment_metrics_handler(arguments: dict | None = None) -> dict[str, Any]:
        start_date, end_date = _date_range(arguments)
        return _with_db(lambda db: payments.payment_metrics(db, organization, start_date, end_date)).model_dump()

    def get_payment_failures_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        start_date, end_date = _date_range(arguments)
        limit = min(max(int(args.get("limit", 50)), 1), 200)
        failures = _with_db(lambda db: payments.payment_failures(db, organization, start_date, end_date, limit))
        return {"failures": [failure.model_dump(mode="json") for failure in failures]}

    def get_payment_recovery_handler(arguments: dict | None = None) -> dict[str, Any]:
        start_date, end_date = _date_range(arguments)
        return _with_db(lambda db: payments.payment_recovery(db, organization, start_date, end_date)).model_dump()

    def get_revenue_at_risk_handler(_arguments: dict | None = None) -> dict[str, Any]:
        return _with_db(lambda db: payments.revenue_at_risk(db, organization)).model_dump()

    def get_customer_payment_history_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        history = _with_db(lambda db: payments.customer_payment_history(db, organization, str(args["customer_id"])))
        return {"history": [entry.model_dump(mode="json") for entry in history]}

    def get_transaction_lifecycle_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        lifecycle = _with_db(lambda db: payments.transaction_lifecycle(db, organization, str(args["order_id"])))
        return {"events": [entry.model_dump(mode="json") for entry in lifecycle]}

    def get_revenue_metrics_handler(arguments: dict | None = None) -> dict[str, Any]:
        start_date, end_date = _date_range(arguments)
        return _with_db(lambda db: payments.revenue_metrics(db, organization, start_date, end_date)).model_dump()

    def get_order_metrics_handler(arguments: dict | None = None) -> dict[str, Any]:
        start_date, end_date = _date_range(arguments)
        return _with_db(lambda db: payments.order_metrics(db, organization, start_date, end_date)).model_dump()

    date_range_schema = {
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"},
        },
        "additionalProperties": False,
    }

    return [
        {
            "name": "get_payment_metrics",
            "description": "Return payment attempt totals, success rate, and succeeded/failed amounts for a date range.",
            "input_schema": date_range_schema,
            "handler": get_payment_metrics_handler,
        },
        {
            "name": "get_payment_failures",
            "description": "Return failed payment attempts with order, customer, failure reason, and recovery status for a date range.",
            "input_schema": {
                **date_range_schema,
                "properties": {**date_range_schema["properties"], "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
            },
            "handler": get_payment_failures_handler,
        },
        {
            "name": "get_payment_recovery",
            "description": "Return recovery attempt totals, recovered amount, and currently open revenue at risk for a date range.",
            "input_schema": date_range_schema,
            "handler": get_payment_recovery_handler,
        },
        {
            "name": "get_revenue_at_risk",
            "description": "Return revenue at risk segmented by recovery outcome: open, recovered, and lost cases with amounts.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "handler": get_revenue_at_risk_handler,
        },
        {
            "name": "get_customer_payment_history",
            "description": "Return the normalized payment history (orders, attempts, refunds, chargebacks, recovery attempts) for a customer.",
            "input_schema": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
                "additionalProperties": False,
            },
            "handler": get_customer_payment_history_handler,
        },
        {
            "name": "get_transaction_lifecycle",
            "description": "Return the full payment lifecycle (order, attempts, refunds, chargebacks, recovery attempts) for an order.",
            "input_schema": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
            "handler": get_transaction_lifecycle_handler,
        },
        {
            "name": "get_revenue_metrics",
            "description": "Return gross revenue minus refunds, chargebacks, and fees for a date range.",
            "input_schema": date_range_schema,
            "handler": get_revenue_metrics_handler,
        },
        {
            "name": "get_order_metrics",
            "description": "Return order count, revenue, and average order value for a date range.",
            "input_schema": date_range_schema,
            "handler": get_order_metrics_handler,
        },
    ]
