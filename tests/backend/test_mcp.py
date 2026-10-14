from fastapi.testclient import TestClient
from uuid import uuid4

from app.db.database import SessionLocal
from app.main import app
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
