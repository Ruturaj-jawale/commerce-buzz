# Data Ingestion Skill

## Purpose

Help transform external commerce/payment data into the universal data model.

## Supported Inputs

- CSV
- Excel
- REST
- PostgreSQL
- Webhooks
- Provider APIs

## Workflow

```text
Inspect
  |
Validate
  |
Map
  |
Normalize
  |
Deduplicate
  |
Queue
  |
Persist
```

## Restrictions

External data is untrusted.

Always validate:

- Organization ownership
- Schema
- Types
- Required fields
- Event type
- External identifier
- Payload size
- Idempotency
