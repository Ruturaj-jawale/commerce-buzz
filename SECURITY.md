# Security

## Security Model

SaaS MCP is a multi-tenant analytics system. Every customer-facing request must resolve to an authenticated organization context.

## Tenant Isolation

All customer data must be scoped by organization.

Never allow:

```text
Organization A -> Organization B data
```

Tenant isolation must be tested explicitly.

## Authentication

Supported development authentication may use organization API keys.

Production should use:

- User accounts
- Cookie-backed sessions for the browser
- OAuth/session authentication for MCP
- Short-lived credentials where appropriate

API keys must not be embedded in frontend/browser bundles.

## Authorization

Authorization must verify:

1. The caller is authenticated.
2. The caller belongs to the organization.
3. The requested resource belongs to that organization.
4. The requested operation is permitted.

## Webhooks

Webhook payloads are untrusted.

Production webhook handling must include:

- Signature verification.
- Replay protection.
- Payload validation.
- Size limits.
- Idempotency.
- Safe error handling.

## Secrets

Never commit:

- API keys
- Database passwords
- OAuth secrets
- Signing secrets
- Deployment secrets
- Customer credentials

Use environment variables or a managed secret store.

## Audit Logging

Audit security-sensitive actions such as:

- API-key creation
- API-key rotation
- Authentication failures
- Organization membership changes
- Authorization failures
- Sensitive data exports
- Administrative operations

## Rate Limiting

Rate limits should apply to:

- Public API
- MCP HTTP endpoints
- Authentication endpoints
- Ingestion endpoints
- Expensive analytics operations

## Data Handling

Raw provider payloads may contain sensitive information. Store only what is required and protect access to raw payloads.

Do not expose raw provider payloads through analytics MCP tools unless explicitly authorized.

## Reporting

Security issues should be reported privately to the project maintainers rather than disclosed publicly before remediation.
