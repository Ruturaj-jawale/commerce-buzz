# AGENTS.md

## Project

SaaS MCP is a multi-tenant, provider-neutral commerce, payments, and revenue-recovery analytics platform.

The primary runtime is `backend/` using FastAPI, SQLAlchemy, and MCP. `frontend/` contains the React + TypeScript + Vite dashboard. `apps/` and `packages/` contain the preserved TypeScript prototype.

## Core Rules

- Keep MCP tools thin.
- MCP tools call services; services own business logic and persistence.
- Treat webhook, API, CSV, Excel, warehouse, and provider payloads as untrusted input.
- Normalize provider data into the universal commerce/payment/recovery model.
- Never expose arbitrary SQL to customer-facing MCP clients.
- Never allow cross-tenant data access.
- Preserve provider metadata without making provider-specific fields part of the core MCP contract.
- Dashboard and MCP must consume the same backend services.
- Provider-specific adapters belong at the ingestion boundary.
- Do not create provider-specific MCP analytics tools.

## Security

Before production:

- Authentication must be required.
- Authorization must be tenant-scoped.
- MCP access must use authenticated user/session or OAuth context.
- API keys must never be embedded in browser code.
- Audit logging must cover security-sensitive operations.
- Rate limiting must be enabled.
- Webhooks must be verified.
- Secrets must not be committed.
- Customer data must not cross organization boundaries.

## Backend

- Use FastAPI routes for transport.
- Put business logic in services.
- Put persistence logic in repositories/models where appropriate.
- Keep database operations organization-scoped.
- Add tests for tenant isolation.
- Prefer explicit schemas for API and MCP inputs/outputs.

## MCP

MCP tools should:

1. Validate input.
2. Resolve authenticated organization/user context.
3. Call a service.
4. Return structured output.
5. Avoid direct SQL.
6. Avoid provider-specific logic.

## Testing

Every security-sensitive feature should include tests for:

- Authorized access.
- Unauthorized access.
- Cross-tenant access.
- Invalid input.
- Missing authentication.
- Failure/retry behavior where applicable.

Run:

```powershell
pytest
```

## Documentation

Update relevant documentation when changing:

- MCP tools
- Universal data model
- Ingestion contracts
- Authentication
- Authorization
- Deployment
- Database migrations
