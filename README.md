# SaaS MCP

SaaS MCP is a universal commerce analytics application. It exposes platform-neutral commerce metrics through MCP tools, resources, and HTTP APIs. A business can connect a warehouse, storefront, or custom application without changing the analytics contract.

A previous TypeScript MCP prototype under `apps/` and `packages/` is preserved and is not the primary Phase 1 runtime.

## Project structure

```text
D:\saas-mcp
├── README.md
├── backend/          FastAPI, SQLAlchemy, MCP server
├── frontend/         React + TypeScript + Vite dashboard
├── tests/backend/    pytest
├── docs/             architecture, API, MCP
├── apps/             preserved TypeScript prototype
└── packages/         preserved TypeScript prototype
```

## Requirements

- Windows 10/11
- Python 3.11+
- Node.js 20+
- PowerShell (preferred for setup commands)

## Installation

All commands below are **PowerShell**. Run them in PowerShell, not Command Prompt.

```powershell
D:
cd D:\saas-mcp
```

### Backend virtual environment

```powershell
cd D:\saas-mcp\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If activation fails with an execution-policy error, stay in PowerShell and run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\.venv\Scripts\Activate.ps1
```

Do not paste `.\.venv\Scripts\Activate.ps1` into Command Prompt. In CMD the equivalent is:

```cmd
D:
cd D:\saas-mcp\backend
.venv\Scripts\activate.bat
```

### Frontend

```powershell
cd D:\saas-mcp\frontend
npm install
```

## Environment configuration

Copy the example files. Never commit `.env`.

PowerShell:

```powershell
Copy-Item D:\saas-mcp\.env.example D:\saas-mcp\.env
Copy-Item D:\saas-mcp\backend\.env.example D:\saas-mcp\backend\.env
Copy-Item D:\saas-mcp\frontend\.env.example D:\saas-mcp\frontend\.env
```

Placeholders include `APP_NAME`, `DATABASE_URL`, `SECRET_KEY`, and MCP server name/version. Replace `SECRET_KEY` before any production use.

### Free database choices

- Local development uses the included free SQLite database by default.
- For a free hosted PostgreSQL development database, create a Supabase project and put its PostgreSQL connection string in `backend/.env` as `DATABASE_URL`, using the `postgresql+psycopg://` form shown in `backend/.env.example`.

Supabase's free plan is suitable for development and pilots, but not permanent production: it has a 500 MB database limit and inactive projects pause after one week.

### Create a development organization

After starting the backend, create an organization once. Copy the returned API key immediately; it is shown only in this response.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/auth/bootstrap -ContentType "application/json" -Body '{"organization_name":"Acme Commerce","organization_slug":"acme-commerce"}'
```

The dashboard does not accept a browser-embedded API key. Sign in through the dashboard login page, which uses a cookie-backed user session (HttpOnly, SameSite=Lax, Secure in production). Machine integrations should use API keys only from trusted server-side code.

Machine integrations can replace a compromised API key through `POST /api/auth/api-keys/rotate` using the current `X-API-Key`. Rotation revokes active keys for that organization and returns the replacement only once. Do not use a machine API key in browser code.

## Quick Start (Run Everything)

From the project root (`D:\saas-mcp`), run:

```powershell
npm start
```

*or*

```powershell
npm run dev
```

This starts both services concurrently:
- **Backend API & Ingestion Worker**: http://127.0.0.1:8000
- **Frontend Dashboard**: http://127.0.0.1:5173

---

## MCP Server Commands

SaaS MCP provides two MCP server runtimes:

### 1. Primary In-Process MCP Server (FastAPI / Python)
The production-ready MCP endpoints are built directly into the FastAPI backend under `/mcp`.
- **Command**: Runs automatically when you run `npm start` (or `npm run dev:backend`).
- **Endpoint**: `http://127.0.0.1:8000/mcp`
- **Key Routes**:
  - `GET /mcp/status` - Server status
  - `GET /mcp/tools` - List available analytics & commerce tools
  - `POST /mcp/tools/{tool_name}` - Invoke an MCP tool
  - `GET /mcp/resources` - List resources

### 2. Standalone TypeScript Prototype MCP Server
To run the preserved standalone TypeScript MCP server (`apps/mcp-server` on port 3001):

```powershell
npm run mcp
```
*or*
```powershell
npm run dev:mcp
```

Server URL: `http://127.0.0.1:3001/mcp`

---

## Running services individually

### Running the backend only

PowerShell:

```powershell
npm run dev:backend
```
*(or manually)*:
```powershell
cd D:\saas-mcp\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

API: http://127.0.0.1:8000  
Health: http://127.0.0.1:8000/health  
Docs: http://127.0.0.1:8000/docs  
MCP: http://127.0.0.1:8000/mcp

### Running the frontend only

PowerShell:

```powershell
npm run dev:frontend
```
*(or manually)*:
```powershell
cd D:\saas-mcp\frontend
npm run dev
```

Dashboard: http://127.0.0.1:5173

## Running tests

PowerShell, from the project root:

```powershell
cd D:\saas-mcp
.\backend\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
pytest
```

## MCP architecture

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

Tools do not contain database or business logic. They call services. See `docs/mcp.md`.

## Product vision: Universal Commerce, Payments, and Revenue Recovery

SaaS MCP is designed to become a provider-neutral commerce and payment intelligence platform. The core data model must remain universal so GoDaddy Commerce, Shopify, Stripe, WooCommerce, Razorpay, PayPal, PostgreSQL, CSV/Excel, webhooks, and custom applications can feed the same analytics contract.

The React dashboard is the human-facing analytics layer, while MCP tools and resources expose the same normalized analytics to AI clients. The product should combine commerce analytics with payment lifecycle and revenue-recovery intelligence rather than becoming only a generic sales dashboard.

### Universal data model

Provider-specific APIs must be translated into universal entities and events such as:

```text
Commerce
  Customer
  Product
  Order
  OrderItem
  Discount
  Tax

Payments
  Payment
  PaymentAttempt
  Transaction
  Refund
  Chargeback
  Fee

Recovery
  RecoveryCase
  RecoveryAttempt
  RecoveryOutcome

Universal Events
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

The normalized model should preserve provider-specific information without making it part of the core contract. Each record should retain source metadata such as provider, account/store identifier, external identifier, external type, and the raw provider payload where appropriate. This allows provider-specific details to be retained while keeping analytics and MCP tools provider-neutral.

### Payment and revenue-recovery intelligence

The platform should track the complete payment lifecycle:

```text
Order
  |
  v
Payment
  |
  +-- Attempt #1 -> FAILED
  |
  +-- Attempt #2 -> FAILED
  |
  +-- Attempt #3 -> SUCCEEDED
                         |
                         v
                      Captured
                         |
                         v
                      Settled
```

Key universal metrics should include payment success/failure rate, failed amount, recovered amount, recovery rate, amount still at risk, time to recovery, retry success rate, refund rate, chargeback rate, fees, and net recovered revenue. A central product metric is **Revenue at Risk / Recoverable Revenue**: the amount associated with failed or otherwise recoverable payment activity, segmented by status, reason, customer, provider, and recovery outcome.

The product should answer questions such as:

- How much revenue was lost or put at risk by failed payments?
- How much was recovered?
- What remains recoverable?
- Why did payments fail?
- Which retry or recovery attempts succeeded?
- How long did recovery take?
- Which customers or orders have the largest recoverable amounts?
- What is the net revenue after refunds, chargebacks, and fees?

### Data ingestion

Users should be able to provide data through multiple ingestion paths while always landing in the same universal model:

```text
GoDaddy Commerce ----+
Shopify -------------+
Stripe --------------+
WooCommerce ---------+
Razorpay ------------+
CSV / Excel ---------+----> Source Adapter / Importer
PostgreSQL -----------+              |
REST API -------------+              v
Webhooks -------------+      Universal Data Model
                                      |
                         +------------+------------+
                         |                         |
                    React Dashboard          MCP Tools/Resources
```

The first practical ingestion path is CSV, Excel, and PDF import with column mapping, validation, and per-row error reporting. A file can be attached to an existing commerce source or create a new tenant-scoped manual source during upload. PDFs with selectable delimited text work by default; scanned/image PDFs can use the optional server-side Tesseract OCR fallback. Files are translated by the declarative mapping engine, so a provider export is a mapping document rather than new adapter code, and native connectors, APIs, and webhooks reuse the same engine without changing the analytics contract.

### MCP contract

MCP tools must remain provider-neutral. Prefer tools such as:

```text
get_payment_metrics
get_payment_failures
get_payment_recovery
get_revenue_at_risk
get_customer_payment_history
get_transaction_lifecycle
get_revenue_metrics
get_order_metrics
```

Do not create separate MCP tools such as `get_stripe_failed_payments()` or `get_godaddy_failed_payments()`. Provider-specific adapters belong at the ingestion boundary; analytics and MCP operate on the universal model.

### React analytics dashboard

The React + TypeScript + Vite dashboard should evolve into a Power BI-style analytics experience with KPI cards, interactive charts, filters, drill-downs, tables, and payment/recovery views. It should show both commerce performance and the movement of money through the payment lifecycle.

A useful top-level dashboard can include:

```text
Revenue | Orders | Customers | Payment Success | Revenue at Risk | Recovered

Revenue Trend        Payment Failures       Recovery Funnel
Sales by Region      Failure Reasons        Recovered vs At Risk
Top Products         Refunds/Chargebacks    Payment Lifecycle
```

The dashboard and MCP should consume the same services and universal data model so a human user and an AI client receive consistent analytics.

### Commerce-source integrations

The product accepts a canonical commerce and payment event regardless of the source. Optional source-specific adapters may be added at the ingestion edge, but they must translate into the same universal contract and must not create source-specific MCP tools.

## Deployment and scaling

The frontend and backend deploy separately: host the Vite frontend on Vercel and the FastAPI backend in the cloud. The application begins as a modular monolith and has a documented path to independently scalable ingestion workers and analytics/MCP services. See [deployment plan](docs/deployment.md) and [architecture](docs/architecture.md).

## Docker

`docker-compose.yml` is optional. Local development uses Python + FastAPI and Node + Vite directly.

## License

See `LICENSE`.
