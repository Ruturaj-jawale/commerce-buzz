# SaaS MCP: Unified Commerce, Interbank Card Switch & Risk Sentinel

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3+-61DAFB.svg?style=flat&logo=React&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.6+-3178C6.svg?style=flat&logo=TypeScript&logoColor=white)](https://www.typescriptlang.org)
[![Model Context Protocol](https://img.shields.io/badge/MCP-2024--11--05-8A2BE2.svg?style=flat)](https://modelcontextprotocol.io)
[![PCI-DSS 3.4](https://img.shields.io/badge/Compliance-PCI--DSS_3.4_Zero--Trust-success.svg)](https://www.pcisecuritystandards.org)
[![Tests](https://img.shields.io/badge/Tests-69%2F69_Passing-brightgreen.svg)](tests/backend)

**SaaS MCP** is a multi-tenant, provider-neutral financial analytics and transaction intelligence platform. It bridges two critical financial domains onto a single universal data model:
1. **Digital Commerce Intelligence**: Order tracking, SKU performance, abandoned checkout dunning, customer retention, and revenue-recovery analytics.
2. **Interbank Card Switch & Risk Sentinel**: ATM cash withdrawals, UPI switches, POS card swipes, interbank settlements, real-time card authorization screening (<45ms SLA), and automated debit-credit reversal reconciliation.

The platform provides dual interfaces:
* **Human Interface**: An adaptive dual-lens React dashboard ("Commerce Analytics" vs "Bank & Card Switch Command Center").
* **AI Agent Interface**: Model Context Protocol (MCP) server providing in-process LLM tools for **Claude Desktop**, **Cursor IDE**, and autonomous agents.

---

## 🌟 Key Capabilities & Architectural Innovations

### 1. Dual-Layer Zero-Trust PII & PCI Sanitization (PCI-DSS 3.4)
* **Pre-Transport Browser Scrubbing**: Client-side sanitizer (`sanitizer.ts`) redacts 16-digit Card PANs, bank accounts, Aadhaar IDs, CVVs, phones, and emails in browser memory before network transmission.
* **Smart Reconciliation Preservation**: Protects and isolates settlement reference numbers (RRN / UTR / Cheque) via tokenization so reversal linking remains 100% operational.
* **Server-Side Ingestion Gatekeeper**: Re-verifies zero-trust masks before any database persistence.

### 2. Automated Reversal & Return Linking Engine
* Solves the bank statement blindspot where failed ATM cash dispensations or reversed POS charges appear as normal credit deposits.
* Uses dual-pass matching (exact RRN match $\to$ fuzzy amount/window match) to atomically flip the prior debit transaction to `failed` (`failure_code: RETURN_REVERSED`), mark the counter transaction as `returned`, and persist an audited `ReversalLink` row.

### 3. Cross-Rail Decline DNA & Behavioral Failure Fingerprinting
* Surfaces the **"Most Failed at Which Name" Leaderboard** of worst-performing merchants and ATM terminals.
* Computes multi-rail failure comparisons (e.g. entity failing 45% on UPI switch but only 2% on Card Swipe), revealing gateway routing bugs versus counterparty solvency risks.

### 4. Real-Time Card Network Middleware (<45ms SLA)
* Operates as an intelligent middleware between card networks and banks:
  $$\text{Mastercard / Visa} \longrightarrow \textbf{SaaS MCP Risk Sentinel} \longrightarrow \text{Issuing Bank}$$
* Evaluates BIN risk, channel velocity, and entity failure history to return instant `APPROVE`, `REVIEW`, or `DECLINE` decisions with reason codes.

### 5. Smart Persona Detection & Adaptive Dual-Lens Surveillance
* Automatically profiles tenant data into `COMMERCE`, `BANK_NETWORK`, or `HYBRID`.
* Dynamically renders either the **Commerce Analytics** view or the **Bank Switch Command Center** (Interbank Settlement Volume, ATM Terminal Failures, Switching Rails, and RRN Reversals).

### 6. Unified 5-Vector Ingestion Switch
* Ingests files across **Excel (.xlsx, .xls)**, **REST API**, **MCP (Model Context Protocol)**, **PDF** (text-based and password-encrypted), and **CSV** with zero-configuration column alias detection.

---

## 📂 Project Structure

```text
saas-mcp/
├── MASTER_SPECIFICATION.md      Comprehensive Master PRD, HLD, LLD & Architectural Spec
├── SETUP.md                     Complete Setup, Installation & Verification Guide
├── MCP_TOOLS_GUIDE.md           Reference manual for all 21 Commerce, Payment & Risk MCP Tools
├── backend/
│   ├── app/
│   │   ├── api/routes/          FastAPI endpoints (auth, risk, imports, webhooks)
│   │   ├── core/                Settings, security, and configuration
│   │   ├── db/                  SQLAlchemy declarative models (Payment, ReversalLink)
│   │   ├── integrations/        Commerce & bank statement adapters
│   │   ├── mcp/                 MCP tools (commerce_tools, payment_tools, risk_tools)
│   │   ├── schemas/             Pydantic models for request/response serialization
│   │   └── services/            PaymentService, RiskService, StatementIngestor
│   └── requirements.txt         Python production & test dependencies
├── frontend/
│   ├── src/
│   │   ├── api/                 API clients (commerce, risk, imports, auth)
│   │   ├── components/          RiskAssessmentPanel, AnalyticsCharts, CsvPreviewGrid
│   │   ├── pages/               Dashboard, ImportWizard (Import Studio)
│   │   └── utils/               sanitizer.ts (Client-side Zero-Trust PII/PCI scrubbing)
│   └── package.json             React, TypeScript, Vite, Tesseract.js
└── tests/backend/               Comprehensive Pytest suite (69/69 passing tests)
```

---

## ⚡ Quick Start (5 Minutes)

### 1. Backend Setup
```powershell
# Activate Python Virtual Environment
backend\.venv\Scripts\Activate.ps1   # Windows
# source backend/.venv/bin/activate    # Linux / macOS

# Install dependencies
pip install -r backend/requirements.txt

# Run automated verification suite (69 tests passing)
pytest

# Start FastAPI & MCP Server
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
* Interactive API Docs: `http://127.0.0.1:8000/docs`
* In-Process MCP Status: `http://127.0.0.1:8000/mcp/status`

### 2. Frontend Dashboard Setup
```powershell
cd frontend
npm install
npm run dev
```
* Dashboard URL: `http://localhost:5173`

For production deployment instructions, database configurations (SQLite / PostgreSQL), and troubleshooting, refer to [`SETUP.md`](SETUP.md).

---

## 🤖 Model Context Protocol (MCP) Integration

SaaS MCP provides **21 tools** that AI models (Claude Desktop, Cursor IDE) can execute to query commerce performance, inspect risk leaderboards, and ingest bank statements.

### Claude Desktop Configuration
Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "saas-mcp": {
      "command": "D:\\saas-mcp\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp.cli"],
      "cwd": "D:\\saas-mcp\\backend",
      "env": {
        "SAAS_MCP_API_KEY": "YOUR_ORGANIZATION_API_KEY"
      }
    }
  }
}
```

### Primary MCP Tool Categories
* **Commerce Analytics Tools** (7 Tools): `list_commerce_sources`, `register_commerce_source`, `ingest_canonical_event`, `get_analytics_summary`, `get_top_products`, `get_customer_metrics`, `get_refund_summary`.
* **Universal Payment & Recovery Tools** (8 Tools): `get_payment_metrics`, `get_payment_failures`, `get_payment_recovery`, `get_revenue_at_risk`, `get_customer_payment_history`, `get_transaction_lifecycle`, `get_revenue_metrics`, `get_order_metrics`.
* **Risk & Interbank Switch Tools** (6 Tools): `get_system_lens`, `get_risk_assessment`, `get_high_risk_entities`, `get_entity_risk_dna`, `evaluate_transaction_risk`, `ingest_statement_file`.

For full schemas, arguments, and return examples, see [`MCP_TOOLS_GUIDE.md`](MCP_TOOLS_GUIDE.md).

---

## 🧪 Testing & Verification

The platform is strictly validated for multi-tenant isolation, automated reversal state transitions, PII/PCI redaction, and sub-45ms middleware SLAs:

```powershell
# Run full automated test suite
pytest

# Run risk sentinel, statement ingestion, and reversal test suites
pytest tests/backend/test_statement_ingestor.py tests/backend/test_risk.py tests/backend/test_reversals.py

# Verify frontend TypeScript compilation and production bundle
npm --prefix frontend run build
```

---

## 📖 Complete Documentation Links

* [**Master System Architecture (PRD / HLD / LLD)**](MASTER_SPECIFICATION.md): Comprehensive system specification, diagrams, mathematical risk formulas, and use cases.
* [**Setup & Installation Guide**](SETUP.md): Environment variables, database setup, and deployment guide.
* [**MCP Tools Reference**](MCP_TOOLS_GUIDE.md): Schema reference and LLM prompt examples for all 21 tools.

---

## 📄 License

This project is licensed under the MIT License — see the `LICENSE` file for details.
