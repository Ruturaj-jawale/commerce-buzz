# SaaS MCP — Progress & Roadmap

Last updated: 2026-10-14. Overall: **~78% complete — Phases 1–3 done, Phase 4 in progress.**

Phases:
1. **Commerce analytics MVP** — done
2. **Security & reliability** — done
3. **Payments & revenue-recovery intelligence** — done
4. **Universal ingestion breadth** — in progress (CSV/Excel import done): declarative mapping presets, MCP Streamable HTTP+OAuth, PostgreSQL
5. **Production operations & monetization** — defined, not started: billing, observability

Test suite: 39 backend tests passing (`pytest`), covering tenant isolation, auth, idempotency, retries, webhooks, file imports, and payment analytics.

---

## Completed

| # | Task | Phase | What shipped |
|---|------|-------|--------------|
| 1 | Project foundation | 1 | FastAPI backend, SQLAlchemy data layer, universal commerce adapter (Shopify/WooCommerce/custom → canonical events), provider-neutral MCP server, SQLite + seeded demo data, React + TypeScript + Vite dashboard wired to the same backend services as MCP |
| 2 | Multi-tenant auth & organization scoping | 2 | Org bootstrap/login, HMAC-hashed API keys, JWT bearer + HttpOnly cookie session with revocation; every query organization-scoped, cross-tenant access returns 404 |
| 3 | Production platform hardening | 2 | API-key rate limiting, audit logging of security-sensitive operations, structured error taxonomy, security headers — enforcing AGENTS.md requirements |
| 4 | Reliable ingestion + background worker | 2 | Durable ingestion-job queue, idempotency, bounded retries with backoff, replay, dead-letter handling, job cancellation; worker runs as an independent deployable unit; API and worker share services |
| 5 | Signed webhook ingestion | 2 | Provider-facing `POST /api/webhooks/sources/{id}` with HMAC-SHA256 signature verification over the raw body (no secret/existence leakage: unconfigured source → 404, bad signature → 401), payload size limits, tenant-scoped jobs |
| 6 | Universal payment & recovery data model | 3 | 9 normalized tables (`orders`, `order_items`, `payments`, `payment_attempts`, `refunds`, `chargebacks`, `fees`, `recovery_cases`, `recovery_attempts`), all organization-scoped; canonical events land into them idempotently via the existing ingest path |
| 7 | Payment lifecycle intelligence service | 3 | `PaymentService` with payment metrics/failures/recovery, revenue-at-risk, customer payment history, transaction lifecycle, revenue & order metrics; failure opens a recovery case, success closes it as recovered, refunds/chargebacks reduce net revenue |
| 8 | MCP payment & recovery tools + tests | 3 | 8 new provider-neutral tools (`get_payment_metrics`, `get_payment_failures`, `get_payment_recovery`, `get_revenue_at_risk`, `get_customer_payment_history`, `get_transaction_lifecycle`, `get_revenue_metrics`, `get_order_metrics`), thin over services, no raw SQL, ISO date ranges; 6 new test suites including MCP end-to-end |
| 9 | Universal file-import workflow | 4 | Upload → preview → column mapping → validate → import → per-row error report → status, for both the dashboard and `/api/imports`. Supports CSV, XLSX, and PDF transaction exports: selectable-text tables work by default, while scanned PDFs use an opt-in Tesseract/Poppler OCR fallback. Source-agnostic declarative mapping engine (column/const targets, dotted paths, line-item grouping, currency/date coercion, name-based mapping suggestions). Imports land through the existing durable queue and canonical contract, so re-imports deduplicate; dashboard import studio included |

## Remaining

| # | Task | Phase | Scope |
|---|------|-------|-------|
| 10 | Declarative mapping presets (GoDaddy first) | 4 | No per-provider adapter code. Reuse the Task 9 mapping engine (field/column mapping config per storefront) for CSV, webhook, and API payloads; GoDaddy/Shopify/etc. ship as JSON presets, users can define their own. Push/CSV-first; pull-mode provider APIs are an optional later add-on |
| 11 | MCP over Streamable HTTP + user session/OAuth | 4 | Replace the legacy REST-style `/mcp` facade with the official Streamable HTTP MCP endpoint carrying authenticated user/org context (required by `docs/mcp.md`) |
| 12 | PostgreSQL + versioned migrations | 4 | Swap SQLite for PostgreSQL with proper migration tooling (Alembic-style), replacing the dev auto-ALTER compatibility loop |
| 13 | Usage-based billing | 5 | Metered usage ingestion, plan tiers, invoicing. Deliberately late: needs real metered usage from live tenants |
| 14 | Observability | 5 | Metrics, tracing, alerting for ingestion and analytics paths. Deliberately late: pays off once the platform is in production |
| 15 | Member roles & permissions | 4 | Beyond tenant-scoping: role-based authorization inside an organization |
| 16 | Verified provider signatures & deployment hardening | 4 | Per-provider webhook signature schemes (Stripe, Shopify, …), secret manager, CI/CD security checks |
| 17 | Dashboard product surfaces | 4 | Finish the dashboard overview, transaction explorer/export, and integration monitoring using the existing provider-neutral services. Third-party OAuth/pull connectors remain optional ingestion adapters, not part of the core analytics contract. |

## Suggested order

10 (mapping presets) → 11 (MCP HTTP+OAuth) → 12 (PostgreSQL) → 15–16 (authz depth, deployment) → **Phase 5:** 13 (billing) → 14 (observability).
