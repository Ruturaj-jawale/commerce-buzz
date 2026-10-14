# Agents

This directory defines specialized AI agents that operate on top of SaaS MCP services.

Agents should not bypass the application's authentication, authorization, tenant, or service layers.

## Agents

- `analytics-agent.md` — general commerce analytics
- `ingestion-agent.md` — ingestion and data-quality workflows
- `payment-agent.md` — payment lifecycle analytics
- `recovery-agent.md` — revenue recovery analytics
- `security-agent.md` — security and tenant-isolation checks

## Agent Rules

Agents:

- Must operate within authenticated organization context.
- Must use approved MCP tools/services.
- Must not execute arbitrary SQL.
- Must not access another tenant.
- Must not modify production data unless the capability explicitly allows it.
- Must provide structured results where possible.
