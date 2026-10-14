"""MCP tools for storefronts and the first-party analytics platform."""

from datetime import date
from typing import Any

from app.db.database import SessionLocal
from app.db.models import Organization
from app.schemas.analytics import CommerceEventIngest
from app.schemas.storefront import StorefrontCreateRequest
from app.services.analytics_service import AnalyticsService
from app.services.storefront_service import StorefrontService


def _with_db(callback):
    db = SessionLocal()
    try:
        return callback(db)
    finally:
        db.close()


def create_storefront_and_analytics_tools(organization: Organization) -> list[dict[str, Any]]:
    storefronts = StorefrontService()
    analytics = AnalyticsService(storefronts)

    def list_sources_handler(_arguments: dict | None = None) -> dict[str, Any]:
        rows = _with_db(lambda db: storefronts.list_storefronts(db, organization))
        return {"sources": [row.model_dump() for row in rows]}

    def register_source_handler(arguments: dict | None = None) -> dict[str, Any]:
        payload = StorefrontCreateRequest.model_validate(arguments or {})
        row = _with_db(lambda db: storefronts.connect(db, organization, payload))
        return row.model_dump()

    def ingest_canonical_event_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        storefront_id = int(args["storefront_id"])
        body = CommerceEventIngest(
            event_name=args.get("event_name"),
            payload=args.get("payload") or {},
        )
        row = _with_db(lambda db: analytics.ingest(db, organization, storefront_id, body))
        return row.model_dump(mode="json")

    def get_analytics_summary_handler(_arguments: dict | None = None) -> dict[str, Any]:
        args = _arguments or {}
        start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
        end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
        summary = _with_db(lambda db: analytics.summary(db, organization, start_date, end_date))
        return summary.model_dump()

    def get_top_products_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
        end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
        limit = min(max(int(args.get("limit", 10)), 1), 100)
        products = _with_db(lambda db: analytics.top_products(db, organization, start_date, end_date, limit))
        return {"products": [product.model_dump() for product in products]}

    def get_customer_metrics_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
        end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
        return _with_db(lambda db: analytics.customer_metrics(db, organization, start_date, end_date)).model_dump()

    def get_refund_summary_handler(arguments: dict | None = None) -> dict[str, Any]:
        args = arguments or {}
        start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
        end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
        return _with_db(lambda db: analytics.refund_summary(db, organization, start_date, end_date)).model_dump()

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
            "name": "list_commerce_sources",
            "description": "List connected commerce data sources. The source can be any commerce platform or warehouse.",
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            "handler": list_sources_handler,
        },
        {
            "name": "register_commerce_source",
            "description": "Register any commerce data source. Source is a human-readable system label, not a fixed provider list.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "source": {"type": "string"},
                    "store_url": {"type": "string"},
                },
                "required": ["name", "source", "store_url"],
                "additionalProperties": False,
            },
            "handler": register_source_handler,
        },
        {
            "name": "ingest_canonical_commerce_event",
            "description": "Store a platform-neutral canonical commerce event. Supply event_name, order_id, revenue, currency, customer_id, items, and optional metadata in payload.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "storefront_id": {"type": "integer"},
                    "event_name": {"type": "string"},
                    "payload": {"type": "object"},
                },
                "required": ["storefront_id"],
                "additionalProperties": False,
            },
            "handler": ingest_canonical_event_handler,
        },
        {
            "name": "get_analytics_summary",
            "description": "Return sales, order, and storefront totals for a date range. Dates are inclusive ISO-8601 dates.",
            "input_schema": date_range_schema,
            "handler": get_analytics_summary_handler,
        },
        {
            "name": "get_top_products",
            "description": "Return products ranked by recorded purchase revenue for a date range.",
            "input_schema": {
                **date_range_schema,
                "properties": {**date_range_schema["properties"], "limit": {"type": "integer", "minimum": 1, "maximum": 100}},
            },
            "handler": get_top_products_handler,
        },
        {
            "name": "get_customer_metrics",
            "description": "Return unique customers, purchase count, revenue, and average order value for a date range.",
            "input_schema": date_range_schema,
            "handler": get_customer_metrics_handler,
        },
        {
            "name": "get_refund_summary",
            "description": "Return refund count, refunded amount, and refund rate for a date range.",
            "input_schema": date_range_schema,
            "handler": get_refund_summary_handler,
        },
    ]
