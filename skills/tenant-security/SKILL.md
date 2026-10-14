# Tenant Security Skill

## Purpose

Validate that analytics and MCP operations remain tenant-scoped.

## Checks

- Authentication exists.
- Organization context exists.
- Resource belongs to organization.
- Requested tool is authorized.
- No cross-tenant records are returned.
- API keys are not exposed to browser code.
- Secrets are not logged.
- Raw provider payloads are protected.

## Required Test Pattern

For any customer-facing data endpoint:

```text
Organization A -> own data -> ALLOW
Organization A -> Organization B data -> DENY
Unauthenticated -> customer data -> DENY
```
