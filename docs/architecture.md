# Architecture

## Current Shape

```text
MCP Client
    |
    v
MCP Server
    |
    +---- MCP Tools
    |
    +---- MCP Resources
    |
    v
Services
    |
    v
Database / External SaaS APIs
```

MCP tools call services and do not own business logic.

## Universal Data Flow

```text
Provider / Warehouse / File / Webhook
                |
                v
       Source Adapter / Importer
                |
                v
       Universal Data Model
                |
        +-------+-------+
        |               |
        v               v
 React Dashboard    MCP Tools/Resources
```

## Deployment Boundary

```text
React Frontend
      |
      v
FastAPI API
      |
      +---- PostgreSQL
      |
      +---- Durable Queue
                 |
                 v
              Worker
```

The frontend and backend deploy independently.

The backend should remain stateless so API instances can scale horizontally.

## Future Scaling

Separate analytics/MCP reads from API writes only when independent scaling becomes necessary.

Move to a managed queue when PostgreSQL queue throughput or retry scheduling becomes insufficient.

## Design Rule

The universal data model is the boundary between provider integrations and analytics.
