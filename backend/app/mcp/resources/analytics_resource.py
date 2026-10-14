"""Analytics summary MCP resource. No credentials."""

from app.db.database import SessionLocal
from app.db.models import Organization
from app.services.analytics_service import AnalyticsService


def create_analytics_summary_resource(organization: Organization) -> dict:
    def reader() -> dict:
        db = SessionLocal()
        try:
            return AnalyticsService().summary(db, organization).model_dump()
        finally:
            db.close()

    return {
        "uri": "analytics://summary",
        "name": "Analytics summary",
        "description": "First-party analytics totals across connected commerce data sources.",
        "mime_type": "application/json",
        "reader": reader,
    }
