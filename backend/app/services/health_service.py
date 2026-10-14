"""Health service used by HTTP and MCP."""

from app.core.config import get_settings


class HealthService:
    def get_status(self) -> dict[str, str]:
        settings = get_settings()
        return {"status": "ok", "service": settings.app_name}