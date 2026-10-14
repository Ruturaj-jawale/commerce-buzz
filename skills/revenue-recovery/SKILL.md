# Revenue Recovery Skill

## Purpose

Analyze recoverable payment activity and revenue recovery performance.

## Key Metrics

```text
Revenue at Risk
Recoverable Revenue
Recovered Amount
Recovery Rate
Time to Recovery
Retry Success Rate
Net Recovered Revenue
```

## Allowed Tools

```text
get_payment_recovery
get_revenue_at_risk
get_transaction_lifecycle
```

## Workflow

1. Determine the date range.
2. Resolve organization context.
3. Retrieve payment/recovery metrics.
4. Segment by supported dimensions.
5. Explain recovered versus still-at-risk amounts.

## Restrictions

Never infer a recovery outcome that is not supported by stored data.
