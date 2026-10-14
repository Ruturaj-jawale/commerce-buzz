# Deployment

## Local Development

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

## Production Shape

```text
Vercel
  |
  v
React Frontend
  |
  v
Cloud FastAPI API
  |
  +---- PostgreSQL
  |
  +---- Queue
          |
          v
        Worker
```

## Readiness

Use:

```text
GET /ready
```

as the backend readiness probe.

## Stateless API

API instances should not depend on local process state for:

- Queue jobs
- Sessions
- Analytics state
- Tenant configuration

Durable state belongs in shared infrastructure.

## Database

Production should use PostgreSQL with versioned migrations.

Required indexes should cover:

- organization
- event time
- queue state
- external identifiers
- idempotency keys

## Future Infrastructure

Consider a managed queue when:

- ingestion volume increases
- retry scheduling becomes complex
- queue throughput exceeds PostgreSQL capacity

Separate analytics/MCP services only when their scaling characteristics require it.
