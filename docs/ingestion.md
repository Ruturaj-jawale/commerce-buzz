# Data Ingestion

All external data enters through an ingestion boundary and is normalized into the universal model.

## Supported / Planned Sources

Live: custom application events (API), HMAC-verified webhooks, CSV and Excel file
imports (through the mapping engine below).

Planned as mapping presets rather than adapter code:

```text
GoDaddy Commerce
Shopify
Stripe
WooCommerce
Razorpay
PayPal
PostgreSQL
REST API
```

## Pipeline

```text
External Source
      |
      v
Source Adapter / Importer
      |
      v
Validation
      |
      v
Canonical Event
      |
      v
Idempotency
      |
      v
Durable Queue
      |
      v
Worker
      |
      v
Universal Data Model
```

## Security

All external payloads are untrusted.

Validate:

- Schema
- Types
- Required fields
- Payload size
- Organization ownership
- External identifiers
- Event type

## Reliability

Production features:

- Idempotency keys
- Deduplication
- Retry limits
- Queue leases
- Dead-letter handling
- Webhook signature verification
- Replay protection
- Import status tracking

## Webhooks

`POST /api/webhooks/sources/{storefront_id}` accepts provider events for a
connected commerce source. It is provider-facing: it does not use
organization credentials. Instead, each source may be configured with a
`webhook_secret` (16-128 characters) at connect time, and every delivery must
include an `X-Signature` header carrying the HMAC-SHA256 of the exact raw
request body, as lowercase hex (a `sha256=<hex>` prefix is also accepted).
Verification is constant-time and the secret is never exposed by the API.

Responses:

- `202 Accepted` — signature verified; the event is durably enqueued and returned as an ingestion job.
- `401 Unauthorized` — missing or invalid signature.
- `404 Not Found` — unknown source, or a source with no `webhook_secret` configured (so the endpoint reveals neither existence nor configuration).
- `413 Payload Too Large` — body exceeds `MAX_INGESTION_PAYLOAD_BYTES` (default 262144).
- `422 Unprocessable Entity` — body is not a valid `CommerceEventIngest`.

Behavior notes:

- The signature covers the raw body bytes exactly as received; providers must not reformat the payload between signing and delivery.
- Enqueued jobs are processed by the same durable ingestion worker and are subject to the same organization-scoping as every other ingestion path; other tenants receive `404` for the job.
- Webhook deliveries are rate limited like all other requests.

## CSV / Excel

File imports run through the same canonical event contract as webhooks and the
API, so imported rows land in the universal data model and are visible to the
same analytics and MCP tools. There is no per-provider import code: a
declarative mapping describes how source columns become canonical fields.

Workflow:

1. **Upload** — `POST /api/imports/sources/{storefront_id}` with a `multipart/form-data`
   `file` part (`.csv` or `.xlsx`, UTF-8, up to `MAX_IMPORT_FILE_BYTES`, default
   5 MiB, and `MAX_IMPORT_ROWS`, default 10000, at most 200 columns). The response
   returns the parsed header row, up to ten sample rows, and a suggested mapping.
2. **Map** — the caller supplies a mapping object; the suggestion matches common
   column names (`Order #`, `Grand Total`, `SKU`, `Qty`, …) automatically.
3. **Validate** — `PUT /api/imports/{batch_id}/mapping` checks the mapping against
   the file's columns and reports per-row issues plus preview canonical payloads.
4. **Import** — `POST /api/imports/{batch_id}/import` enqueues one durable ingestion
   job per mapped event, tagged with the batch and its 1-based source row.
5. **Status** — `GET /api/imports/{batch_id}` returns batch state, validation issues,
   and per-job errors. A batch finalizes once the worker has drained its jobs.

Mapping shape:

```json
{
  "event_name": { "const": "purchase" },
  "order_id": { "column": "Order #" },
  "revenue": { "column": "Total" },
  "currency": { "column": "Currency" },
  "customer_id": { "column": "Email" },
  "occurred_at": { "column": "Date" },
  "items": {
    "product_id": { "column": "SKU" },
    "name": { "column": "Product" },
    "price": { "column": "Price" },
    "quantity": { "column": "Qty" }
  }
}
```

Each target takes either `{"column": "..."}` or `{"const": ...}`. Columns support
dotted paths (`total.amount`) so the same engine maps nested webhook or API
payloads, which is how provider presets will work: a GoDaddy or Shopify export is
a mapping document, not an adapter.

Behavior notes:

- With an `items` mapping, rows are grouped by `order_id` and each row contributes
  one line item; order-level fields come from the first row of each group. Without
  `items`, one row becomes one event.
- Currency symbols, thousands separators, and accounting negatives such as
  `(1234.50)` are coerced; dates accept ISO `YYYY-MM-DD` plus common locale formats.
- Re-importing a file is safe: the canonical adapter derives an idempotency key
  from the event name and order id, so duplicates are deduplicated.
- Imported rows are only counted once they pass validation; a batch whose rows all
  fail cannot be started.
- Batches are organization-scoped; another tenant receives `404` for the batch, and
  uploading to another tenant's source also returns `404`.
- `occurred_at` is currently stamped at ingest time by the analytics event store, so
  a mapped historical date does not yet change event ordering.

## Adapter Rule

Adapters translate provider data into the universal model.

They must not introduce provider-specific MCP analytics tools.
