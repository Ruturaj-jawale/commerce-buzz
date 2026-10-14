# Contributing

## Development Principles

SaaS MCP is designed around a provider-neutral universal analytics contract.

Contributions should preserve:

- Multi-tenancy.
- Tenant isolation.
- Thin MCP tools.
- Service-owned business logic.
- Canonical event normalization.
- Provider-neutral analytics.
- Testability.
- Secure handling of untrusted input.

## Where Code Belongs

### MCP tools

Use MCP tools for transport and input/output handling.

Do not place:

- Complex analytics
- SQL queries
- Provider-specific transformations
- Authorization rules that belong in shared services

inside tools.

### Services

Services own:

- Analytics calculations
- Business rules
- Normalization
- Persistence workflows
- Queue operations

### Adapters

Adapters translate provider-specific payloads into the universal data model.

Examples:

```text
Shopify Adapter
Stripe Adapter
WooCommerce Adapter
Razorpay Adapter
CSV Importer
PostgreSQL Importer
Webhook Adapter
```

Adapters must not create provider-specific MCP analytics tools.

## Pull Requests

A change should include:

- Tests.
- Documentation changes when contracts change.
- Migration files for schema changes.
- Security/tenant tests for access-control changes.

## Database Changes

Do not make production schema changes without a versioned migration.

New indexes should be evaluated for:

- organization/tenant filtering
- event time
- queue state
- external identifiers
- idempotency keys

## MCP Contract Changes

When changing an MCP tool:

- Document the input.
- Document the output.
- Document errors.
- Preserve tenant isolation.
- Avoid provider-specific naming.
