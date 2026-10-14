# Payment Analytics Skill

## Purpose

Analyze payment performance across providers using the universal payment model.

## Questions

The skill should support questions such as:

- What is the payment success rate?
- How much failed?
- Why did payments fail?
- Which payment attempts succeeded?
- What fees were incurred?

## Allowed Tools

```text
get_payment_metrics
get_payment_failures
get_customer_payment_history
get_transaction_lifecycle
```

## Restrictions

- Provider-neutral.
- Tenant-scoped.
- No arbitrary SQL.
- No invented data.
