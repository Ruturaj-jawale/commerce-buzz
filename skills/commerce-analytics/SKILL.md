# Commerce Analytics Skill

## Purpose

Answer commerce analytics questions using provider-neutral MCP analytics tools.

## Inputs

Possible inputs:

- Date range
- Organization context
- Product filters
- Customer filters
- Region filters
- Metric selection

## Allowed Tools

```text
get_sales_summary
get_top_products
get_customer_metrics
get_refund_summary
get_revenue_metrics
get_order_metrics
```

## Workflow

1. Validate the requested date range and filters.
2. Use the authenticated organization context.
3. Call the appropriate analytics service/tool.
4. Return structured metrics.
5. Explain missing or incomplete data.

## Restrictions

- No arbitrary SQL.
- No cross-tenant access.
- No provider-specific tool selection.
