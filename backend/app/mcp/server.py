"""In-process MCP server and HTTP adapter. Tools call services, not the database."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import Organization
from app.mcp.resources.analytics_resource import create_analytics_summary_resource
from app.mcp.resources.system_resource import create_system_info_resource
from app.mcp.tools.commerce_tools import create_storefront_and_analytics_tools
from app.mcp.tools.health_tool import create_health_check_tool
from app.mcp.tools.payment_tools import create_payment_tools
from app.services.health_service import HealthService


class McpServer:
    def __init__(self, name: str, version: str) -> None:
        self.name = name
        self.version = version
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}

    def register_tool(self, tool: dict[str, Any]) -> None:
        self._tools[tool["name"]] = tool

    def register_resource(self, resource: dict[str, Any]) -> None:
        self._resources[resource["uri"]] = resource

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"],
            }
            for tool in self._tools.values()
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Unknown MCP tool: {name}")
        return tool["handler"](arguments or {})

    def list_resources(self) -> list[dict[str, Any]]:
        return [
            {
                "uri": resource["uri"],
                "name": resource["name"],
                "description": resource["description"],
                "mime_type": resource["mime_type"],
            }
            for resource in self._resources.values()
        ]

    def read_resource(self, uri: str) -> dict[str, Any]:
        resource = self._resources.get(uri)
        if resource is None:
            raise KeyError(f"Unknown MCP resource: {uri}")
        return resource["reader"]()


def create_mcp_server(organization: Organization) -> McpServer:
    settings = get_settings()
    server = McpServer(name=settings.mcp_server_name, version=settings.mcp_server_version)
    server.register_tool(create_health_check_tool(HealthService()))
    for tool in create_storefront_and_analytics_tools(organization):
        server.register_tool(tool)
    for tool in create_payment_tools(organization):
        server.register_tool(tool)
    server.register_resource(create_system_info_resource(settings))
    server.register_resource(create_analytics_summary_resource(organization))
    return server


mcp_router = APIRouter(prefix="/mcp", tags=["mcp"])


@mcp_router.get("/status")
def mcp_status(organization: Organization = Depends(get_current_organization)) -> dict[str, str]:
    return {
        "status": "available",
        "server": get_settings().mcp_server_name,
        "version": get_settings().mcp_server_version,
    }


@mcp_router.get("/tools")
def list_mcp_tools(organization: Organization = Depends(get_current_organization)) -> dict[str, Any]:
    return {"tools": create_mcp_server(organization).list_tools()}


@mcp_router.post("/tools/{tool_name}")
def invoke_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None, organization: Organization = Depends(get_current_organization)) -> dict[str, Any]:
    try:
        return {"result": create_mcp_server(organization).call_tool(tool_name, arguments)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@mcp_router.get("/resources")
def list_mcp_resources(organization: Organization = Depends(get_current_organization)) -> dict[str, Any]:
    return {"resources": create_mcp_server(organization).list_resources()}


@mcp_router.get("/resource")
def read_mcp_resource(uri: str, organization: Organization = Depends(get_current_organization)) -> dict[str, Any]:
    try:
        return {"uri": uri, "contents": create_mcp_server(organization).read_resource(uri)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
