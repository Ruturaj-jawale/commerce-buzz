# Universal Data Model

SaaS MCP uses a provider-neutral model for commerce, payments, and revenue recovery.

## Commerce

```text
Customer
Product
Order
OrderItem
Discount
Tax
```

## Payments

```text
Payment
PaymentAttempt
Transaction
Refund
Chargeback
Fee
```

## Recovery

```text
RecoveryCase
RecoveryAttempt
RecoveryOutcome
```

## Universal Events

```text
order_created
payment_attempted
payment_failed
payment_succeeded
payment_captured
payment_settled
refund_created
chargeback_created
recovery_attempted
recovery_succeeded
```

## Provider Metadata

Normalized records may retain:

```text
provider
account/store identifier
external identifier
external type
raw provider payload
```

Provider-specific metadata is retained at the integration boundary and must not change the provider-neutral analytics contract.

## Design Rule

A Stripe payment and a Shopify payment must become compatible with the same analytics services after normalization.

Do not create separate analytics contracts for each provider.

## Implementation Status

The normalized payment/recovery model is live. `AnalyticsService.ingest` lands every payment-lifecycle canonical event into the normalized tables through `PaymentService.land_event`:

- `purchase` / `order_created` upsert the order (`purchase` marks it paid and replaces its line items).
- `payment_attempted` / `payment_failed` / `payment_succeeded` upsert the payment and record one `PaymentAttempt` with the matching status. `payment_failed` also opens a `RecoveryCase` for the order.
- `payment_captured` / `payment_settled` advance the payment status and close any open recovery case as recovered.
- `refund` / `refund_created` append a `Refund` and move the order to `partially_refunded` or `refunded`.
- `chargeback_created` appends a `Chargeback` and marks the payment `chargeback`.
- `recovery_attempted` / `recovery_succeeded` append a `RecoveryAttempt`; success closes the case as recovered.

Landing is idempotent: normalized rows are keyed by the event idempotency key (or a deterministic external reference such as `payment:<ref>` / `case:<ref>`), so duplicate deliveries and worker retries converge instead of double-counting. Events without an `order_id` or idempotency anchor stay in the event stream but do not land in the normalized model.

`Customer`, `Product`, `Discount`, `Tax`, `Transaction`, and `RecoveryOutcome` remain event-stream or planned concepts; `Fee` exists as a table and feeds net-revenue metrics once fee records are ingested.
