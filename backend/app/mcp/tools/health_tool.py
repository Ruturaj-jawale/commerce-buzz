"""Health MCP tool. Delegates to HealthService."""

from collections.abc import Callable

from app.services.health_service import HealthService


def create_health_check_tool(service: HealthService | None = None) -> dict:
    health_service = service or HealthService()

    def handler(_arguments: dict | None = None) -> dict[str, str]:
        return health_service.get_status()

    return {
        "name": "health_check",
        "description": "Return application health status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": handler,
    }


def health_check_handler(service: HealthService | None = None) -> Callable[..., dict[str, str]]:
    return create_health_check_tool(service)["handler"]
