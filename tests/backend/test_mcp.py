import json
from uuid import uuid4
from fastapi.testclient import TestClient

from app.db.database import SessionLocal
from app.main import app
from app.mcp.cli import process_message, resolve_organization
from app.mcp.server import create_mcp_server
from app.services.auth_service import AuthService


client = TestClient(app)


def create_tenant() -> tuple[dict[str, str], object]:
    suffix = uuid4().hex[:12]
    response = client.post("/api/auth/bootstrap", json={"organization_name": f"MCP {suffix}", "organization_slug": f"mcp-{suffix}"})
    assert response.status_code == 201
    api_key = response.json()["api_key"]["key"]
    db = SessionLocal()
    try:
        organization = AuthService().organization_for_key(db, api_key)
        db.expunge(organization)
        return {"X-API-Key": api_key}, organization
    finally:
        db.close()


def test_health_check_tool() -> None:
    _, organization = create_tenant()
    server = create_mcp_server(organization)
    result = server.call_tool("health_check")
    assert result == {"status": "ok", "service": "saas-mcp"}


def test_system_info_resource() -> None:
    _, organization = create_tenant()
    server = create_mcp_server(organization)
    result = server.read_resource("system://info")
    assert result["name"] == "saas-mcp"
    assert result["version"] == "0.1.0"
    assert "environment" in result
    assert "SECRET_KEY" not in result
    assert "secret" not in {key.lower() for key in result}


def test_mcp_http_status_and_resource() -> None:
    headers, _ = create_tenant()
    status = client.get("/mcp/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["status"] == "available"

    resource = client.get("/mcp/resource", params={"uri": "system://info"}, headers=headers)
    assert resource.status_code == 200
    assert resource.json()["contents"]["name"] == "saas-mcp"


def test_mcp_stdio_cli_json_rpc() -> None:
    headers, organization = create_tenant()
    api_key = headers["X-API-Key"]
    resolved_org = resolve_organization(api_key=api_key)
    assert resolved_org.id == organization.id

    server = create_mcp_server(organization)

    # 1. Test initialize
    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    init_resp = process_message(init_req, server)
    assert init_resp["id"] == 1
    assert init_resp["result"]["serverInfo"]["name"] == "saas-mcp"
    assert "tools" in init_resp["result"]["capabilities"]

    # 2. Test ping
    ping_resp = process_message(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}), server)
    assert ping_resp["id"] == 2
    assert ping_resp["result"] == {}

    # 3. Test tools/list
    tools_resp = process_message(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}), server)
    assert tools_resp["id"] == 3
    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert "health_check" in tool_names
    assert "evaluate_transaction_risk" in tool_names
    assert "ingest_statement_file" in tool_names
    for t in tools_resp["result"]["tools"]:
        assert "inputSchema" in t

    # 4. Test tools/call (success)
    call_resp = process_message(
        json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "health_check", "arguments": {}}}),
        server,
    )
    assert call_resp["id"] == 4
    assert call_resp["result"]["isError"] is False
    assert "ok" in call_resp["result"]["content"][0]["text"]

    # 5. Test tools/call (error handling)
    err_resp = process_message(
        json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "non_existent_tool"}}),
        server,
    )
    assert err_resp["id"] == 5
    assert err_resp["result"]["isError"] is True

    # 6. Test resources/list
    res_list_resp = process_message(json.dumps({"jsonrpc": "2.0", "id": 6, "method": "resources/list"}), server)
    assert res_list_resp["id"] == 6
    uris = [r["uri"] for r in res_list_resp["result"]["resources"]]
    assert "system://info" in uris
    assert "analytics://summary" in uris

    # 7. Test resources/read
    read_resp = process_message(
        json.dumps({"jsonrpc": "2.0", "id": 7, "method": "resources/read", "params": {"uri": "system://info"}}),
        server,
    )
    assert read_resp["id"] == 7
    assert "saas-mcp" in read_resp["result"]["contents"][0]["text"]
