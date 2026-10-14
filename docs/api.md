# HTTP API

Base URL (local): `http://127.0.0.1:8000`

Interactive docs: `http://127.0.0.1:8000/docs`

All endpoints are organization-scoped. Authenticate with `X-API-Key` or the cookie-backed user session; cross-tenant access returns 404.

## Implemented

### Health

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Process liveness |
| `GET /ready` | Readiness |

### Auth — `/api/auth`

| Method & path | Purpose |
| --- | --- |
| `POST /api/auth/bootstrap` | Create organization, first user, and API key (shown once) |
| `POST /api/auth/login` | Start user session (HttpOnly cookie) |
| `GET /api/auth/me` | Current user, organization, memberships |
| `POST /api/auth/logout` | End session |
| `POST /api/auth/api-keys/rotate` | Rotate the organization's API key (revokes active keys, returns replacement once) |

### Commerce sources — `/api/commerce-sources`

| Method & path | Purpose |
| --- | --- |
| `GET /api/commerce-sources` | List connected sources |
| `POST /api/commerce-sources` | Connect a source (name, provider, store URL, optional webhook secret) |

### Analytics — `/api/analytics`

| Method & path | Purpose |
| --- | --- |
| `GET /api/analytics/summary` | Revenue summary with optional `start_date`/`end_date` |
| `GET /api/analytics/top-products` | Product metrics, optional date range and `limit` |
| `GET /api/analytics/customer-metrics` | Customer/order/AOV aggregates, optional date range |
| `GET /api/analytics/refund-summary` | Refund aggregates, optional date range |
| `GET /api/analytics/events` | Recent canonical events |
| `POST /api/analytics/sources/{storefront_id}/events` | Ingest one canonical event synchronously |
| `POST /api/analytics/sources/{storefront_id}/ingestion-jobs` | Queue an event for the background worker (202) |
| `GET /api/analytics/ingestion-jobs/{job_id}` | Job status (tenant-scoped) |
| `POST /api/analytics/sources/{storefront_id}/sample-purchase` | Seed a sample purchase event |

### Webhooks — `/api/webhooks`

| Method & path | Purpose |
| --- | --- |
| `POST /api/webhooks/sources/{storefront_id}` | Verified provider webhook ingestion (HMAC-SHA256 over raw body, `X-Signature: sha256=...`). 202 on accept; 401 bad signature; 404 unknown source or no webhook secret configured; 413 oversized payload; 422 invalid payload |

### Imports — `/api/imports`

| Method & path | Purpose |
| --- | --- |
| `POST /api/imports/sources/{storefront_id}` | Upload a `.csv`/`.xlsx` order export (multipart `file`); returns parsed columns, sample rows, and a suggested column mapping |
| `GET /api/imports` | List recent import batches for the organization |
| `GET /api/imports/{batch_id}` | Batch status, validation issues, and per-row job errors |
| `PUT /api/imports/{batch_id}/mapping` | Set the declarative mapping and validate it; returns row counts, issues, and preview canonical payloads |
| `POST /api/imports/{batch_id}/import` | Enqueue one ingestion job per mapped event (idempotent on re-run) |

See `docs/ingestion.md` for the mapping format and coercion rules. 413 covers
oversized files, 422 covers unparseable files, bad mappings, and imports started
before validation.

### MCP facade (legacy)

| Method & path | Purpose |
| --- | --- |
| `GET /mcp/status` | In-process MCP server status, used by the dashboard |
| `GET /mcp/tools` | List registered MCP tools |
| `POST /mcp/tools/{tool_name}` | Invoke a tool through the MCP server |
| `GET /mcp/resources` | List registered MCP resources |
| `GET /mcp/resource?uri=system://info` | Read a resource (query parameter avoids Windows URL issues with `://`) |

The legacy REST-style facade is to be replaced by the official Streamable HTTP MCP endpoint with user-session/OAuth authentication (see `docs/mcp.md`).

## Planned (not implemented)

| Path | Purpose |
| --- | --- |
| `/api/billing` | Billing (Phase 5) |
| `/api/users` | User management |
| `/api/organizations` | Organization management |
| `/api/integrations` | Connected SaaS accounts |
