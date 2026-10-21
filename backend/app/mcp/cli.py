"""Model Context Protocol (MCP) stdio server CLI.

Provides standard JSON-RPC 2.0 stdio transport compatible with Claude Desktop,
Cursor IDE, and autonomous AI agents.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# Ensure backend root is in sys.path even when cli.py is invoked directly
_backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.core.config import get_settings
from app.db.database import SessionLocal, init_db
from app.db.models import Organization
from app.mcp.server import McpServer, create_mcp_server
from app.services.auth_service import AuthService

logger = logging.getLogger("saas-mcp-stdio")
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(logging.Formatter("[MCP stdio] %(levelname)s: %(message)s"))
logger.addHandler(_handler)
logger.setLevel(logging.INFO)


def handle_initialize(req_id: Any, _params: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False,
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": False,
                },
            },
            "serverInfo": {
                "name": settings.mcp_server_name,
                "version": settings.mcp_server_version,
            },
        },
    }


def handle_ping(req_id: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": {}}


def handle_tools_list(req_id: Any, server: McpServer) -> dict[str, Any]:
    tools = []
    for tool in server.list_tools():
        tools.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "inputSchema": tool.get("input_schema") or tool.get("inputSchema") or {"type": "object", "properties": {}},
        })
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"tools": tools},
    }


def handle_tools_call(req_id: Any, params: dict[str, Any], server: McpServer) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    try:
        res = server.call_tool(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(res, indent=2, default=str),
                    }
                ],
                "isError": False,
            },
        }
    except Exception as exc:
        logger.exception("Error executing tool %s", name)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing tool '{name}': {str(exc)}",
                    }
                ],
                "isError": True,
            },
        }


def handle_resources_list(req_id: Any, server: McpServer) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {"resources": server.list_resources()},
    }


def handle_resources_read(req_id: Any, params: dict[str, Any], server: McpServer) -> dict[str, Any]:
    uri = params.get("uri")
    try:
        data = server.read_resource(uri)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": json.dumps(data, indent=2, default=str),
                    }
                ],
            },
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32002,
                "message": f"Resource error: {str(exc)}",
            },
        }


def resolve_organization(api_key: str | None = None) -> Organization:
    init_db()
    with SessionLocal() as db:
        resolved_key = (api_key or os.environ.get("SAAS_MCP_API_KEY") or "").strip()
        auth_service = AuthService()
        if resolved_key:
            return auth_service.organization_for_key(db, resolved_key)

        settings = get_settings()
        if settings.app_env != "production":
            first_org = db.query(Organization).first()
            if first_org:
                logger.info(
                    "No SAAS_MCP_API_KEY provided; automatically using dev organization '%s' (id=%d)",
                    first_org.name,
                    first_org.id,
                )
                return first_org

        raise ValueError(
            "Authentication required: SAAS_MCP_API_KEY environment variable or --api-key argument must be provided."
        )


def process_message(line: str, server: McpServer) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        req = json.loads(line)
    except json.JSONDecodeError as err:
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32700, "message": f"Parse error: {err}"},
        }

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return handle_initialize(req_id, params)
    if method == "ping":
        return handle_ping(req_id)
    if method == "tools/list":
        return handle_tools_list(req_id, server)
    if method == "tools/call":
        return handle_tools_call(req_id, params, server)
    if method == "resources/list":
        return handle_resources_list(req_id, server)
    if method == "resources/read":
        return handle_resources_read(req_id, params, server)

    if req_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
    return None


def run_stdio_server(server: McpServer, input_stream=sys.stdin, output_stream=sys.stdout) -> None:
    for line in input_stream:
        resp = process_message(line, server)
        if resp is not None:
            output_stream.write(json.dumps(resp) + "\n")
            output_stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="SaaS MCP stdio server")
    parser.add_argument("--api-key", default=None, help="Organization API key")
    args = parser.parse_args()

    try:
        org = resolve_organization(args.api_key)
        server = create_mcp_server(org)
        logger.info(
            "SaaS MCP server '%s' started for org '%s' (%d tools registered)",
            server.name,
            org.name,
            len(server.list_tools()),
        )
        run_stdio_server(server)
    except Exception as exc:
        logger.error("Failed to start SaaS MCP server: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
