"""System information MCP resource. Never includes secrets."""

from app.core.config import Settings, get_settings


def create_system_info_resource(settings: Settings | None = None) -> dict:
    app_settings = settings or get_settings()

    def reader() -> dict[str, str]:
        return {
            "name": app_settings.app_name,
            "version": app_settings.app_version,
            "environment": app_settings.app_env,
        }

    return {
        "uri": "system://info",
        "name": "System info",
        "description": "Application name, version, and environment.",
        "mime_type": "application/json",
        "reader": reader,
    }
