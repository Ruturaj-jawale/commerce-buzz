# MCP Contract

MCP exposes provider-neutral analytics through tools and resources.

## Principles

- Tools are thin.
- Services own analytics.
- Requests are tenant-scoped.
- Inputs are validated.
- Outputs are structured.
- Arbitrary SQL is never exposed.
- Provider-specific tools are not created.

## Analytics Tools

```text
get_sales_summary
get_top_products
get_customer_metrics
get_refund_summary
get_payment_metrics
get_payment_failures
get_payment_recovery
get_revenue_at_risk
get_customer_payment_history
get_transaction_lifecycle
get_revenue_metrics
get_order_metrics
```

## Date Filtering

Business analytics tools should support optional inclusive ISO-8601 date ranges where applicable.

Example:

```json
{
  "start_date": "2026-09-01",
  "end_date": "2026-09-30"
}
```

## Authentication

Customer-facing MCP HTTP access must resolve authenticated user and organization context.

The legacy REST-style `/mcp` facade should be replaced by the official Streamable HTTP MCP endpoint with user-session/OAuth authentication.

## Authorization

Before executing an analytics tool:

```text
Authenticate
    |
Resolve User
    |
Resolve Organization
    |
Authorize Tool
    |
Execute Service
    |
Return Structured Result
```

## Error Handling

Return structured errors for:

- Authentication failure
- Authorization failure
- Invalid date range
- Invalid filters
- Missing resource
- Ingestion not ready
- Internal analytics failure

Never expose SQL, stack traces, secrets, or cross-tenant records.
