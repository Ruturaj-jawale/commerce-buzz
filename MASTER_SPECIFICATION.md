# SaaS MCP: Unified Commerce, Interbank Card Network Switch & Risk Sentinel Platform
## Master Product Requirements Document (PRD), High-Level Design (HLD) & Low-Level Design (LLD)

---

## 1. Executive Summary & Vision

**SaaS MCP** is an enterprise-grade, multi-tenant financial infrastructure and surveillance platform that unifies two traditionally segregated financial worlds onto a single universal data model:

1. **E-Commerce & Digital Commerce Analytics**: Storefront connectivity (Shopify, custom storefronts, warehouses), canonical order event ingestion, gross merchandise value (GMV), average order value (AOV), SKU velocity, customer lifetime value, and automated abandoned checkout / payment recovery cases.
2. **Interbank Card Network & Clearing Switch**: Interbank clearing and settlement surveillance, ATM cash withdrawal monitoring, UPI switches, POS card swipes, online gateway routing, sub-45ms real-time card authorization screening middleware, and automated debit-credit reversal reconciliation.

The platform bridges both worlds through **Autonomous AI via the Model Context Protocol (MCP)**:
- **Dual Transport Architecture**: Native **stdio JSON-RPC 2.0** server (`python -m app.mcp.cli`) for desktop AI tools (**Claude Desktop**, **Cursor IDE**, Zed, Cline) and **HTTP REST API** (`/mcp/*`) for web agents and programmatic orchestrators.
- **22 Production Tools & 2 System Resources**: Covering health monitoring, commerce source management, normalized event ingestion, revenue recovery, rail-specific decline DNA, real-time risk evaluation, and zero-trust bank statement ingestion.

---

## 2. Product Requirements Document (PRD)

### 2.1 Problem Statement
Modern businesses, card networks, and financial institutions face deeply fragmented architectures:
* **E-Commerce Brands & CFOs** lack visibility into root-cause payment failures at the clearing switch rail, losing revenue to false declines and uncoordinated recovery attempts.
* **Banks, ATM Operators & Card Processors** process millions of unstructured bank statement narrations (SBI, HDFC, ICICI, Axis, IPPB) where failed ATM cash dispensations and reversed POS swipes look like ordinary credit deposits, obscuring true rail failure rates and giving rise to phantom reversal fraud.
* **Regulatory Compliance & Privacy Mandates (PCI-DSS 3.4, GDPR, RBI PII Directives)** strictly forbid storing 16-digit Primary Account Numbers (PANs), bank account numbers, Aadhaar IDs, and CVVs in plaintext. Sensitive data must be neutralized **client-side before network transmission** and **server-side before SQL persistence**.

### 2.2 Core Personas & User Stories
| Persona | Key Need | Platform Capability |
|---|---|---|
| **E-Commerce Merchant / CFO** | Track revenue, SKU sales, refunds, and recover abandoned checkouts. | Adaptive Commerce Lens rendering GMV, AOV, top products, customer metrics, and automated recovery cases. |
| **Card Network & Switch Analyst** | Monitor interbank clearing volumes, rail failure rates, and hardware terminal failures. | Adaptive Bank Switch Command Center, RRN/UTR reconciliation, and ATM failure tracking. |
| **Risk & Fraud Operations Officer** | Identify chronic counterparty failure rates and stop phantom reversal loops. | "Most Failed at Which Name" Leaderboard, Cross-Rail Decline DNA, and Sub-45ms Screening Middleware. |
| **Autonomous AI Financial Agent** | Analyze portfolio risk, inspect counterparties, and ingest statement files. | 22 thin MCP tools (`get_risk_assessment`, `evaluate_transaction_risk`, `ingest_statement_file`, `get_entity_risk_dna`). |

### 2.3 Functional Requirements
1. **Multi-Vector Statement & Event Ingestion**:
   - **Excel (.xlsx / .xls)**: Multi-sheet statements parsed via `openpyxl`/`xlrd` with auto-detected debit/credit columns.
   - **CSV / TXT**: Streaming client pre-parsing and backend `csv.DictReader` normalization.
   - **PDF**: Text and password-encrypted PDFs processed via `pdfplumber`, `pypdf`, and `pikepdf` with OCR fallback.
   - **REST API Uploads**: Multipart batch ingestion (`/api/analytics/statements/upload`, `/api/imports/file`).
   - **Model Context Protocol (MCP)**: Local file path ingestion (`ingest_statement_file`) for attached LLMs.
2. **Dual-Layer Zero-Trust PII & PCI Sanitization**:
   - **Client-Side Pre-Transport Scrubbing** (`sanitizer.ts`): Card PANs, bank accounts, Aadhaar, CVVs, phones, and emails are masked in browser memory before network transit.
   - **Server-Side Gatekeeper** (`statement_parser.py`): Ingestion-layer regex verification ensuring zero plaintext PII/PCI reaches SQLite/PostgreSQL.
   - **Reconciliation Token Preservation**: Preserves RRN, UTR, and Cheque reference codes via tokenized placeholders.
3. **Automated Debit-Credit Reversal Linking Engine**:
   - Dual-pass reconciliation: Exact RRN/UTR match with fallback to amount + fuzzy entity within a 30-day temporal window.
   - Atomic state transitions: Debit marked `failed`, credit marked `returned`, and audited `ReversalLink` created.
4. **Sub-45ms Real-Time Card Network Screening Middleware**:
   - Real-time authorization evaluation (`APPROVE`, `REVIEW`, `DECLINE`) with risk scoring, BIN check, and reason codes.
5. **Adaptive Surveillance Perspective**:
   - Auto-detection profiling organizations as `COMMERCE`, `BANK_NETWORK`, or `HYBRID`.

### 2.4 Non-Functional Requirements
- **Latency SLA**: Real-time card screening evaluation completes in `< 45ms`.
- **Multi-Tenant Isolation**: Strict `organization_id` scoping across all DB queries, MCP tools, and sessions. Zero cross-tenant data leakage.
- **Security & Cryptography**: High-entropy JWT session tokens (HttpOnly, SameSite), HMAC-SHA256 API keys with pepper, and constant-time webhook signature verification.
- **Test Suite Verification**: 100% verification across all critical paths (**71/71 automated backend tests passing**).

---

## 3. High-Level Design (HLD)

### 3.1 End-to-End System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Multi-Vector Ingestion & Zero-Trust Boundary"]
        F1["Excel (.xlsx, .xls)"]
        F2["CSV Statements"]
        F3["PDF Statements"]
        F4["REST API Uploads"]
        F5["MCP Stdio File Tool"]
        ClientSanitizer["Client-Side Sanitizer\n(Browser Memory Masking)"]
        ServerSanitizer["Server-Side Gatekeeper\n(PCI-DSS 3.4 Ingestion Filter)"]
    end

    subgraph AsyncQueue["2. Durable Asynchronous Ingestion Queue"]
        JobTable["IngestionJob Table\n(status: queued, processing, completed, failed)"]
        Worker["In-Process Async Worker Loop\n(Thread-Pool DB Executor & SAVEPOINT Isolation)"]
    end

    subgraph CoreEngine["3. Normalization, Reversal & Risk Engine"]
        Parser["Narration Parser & Classifier\n(Channel, Entity, RRN, Direction)"]
        ReversalEngine["Automated Reversal\nLinking Engine"]
        PaymentService["Normalized Universal\nPayment Service"]
        RiskService["Risk Assessment Sentinel\n& Leaderboard Engine"]
        DeclineDNA["Cross-Rail Decline DNA\nFingerprinting"]
        LensDetector["System Lens Auto-Detection\n(Commerce vs Bank Switch)"]
    end

    subgraph Interfaces["4. Consumption & Integration Surfaces"]
        StdioMCP["MCP Stdio CLI Server\n(Claude Desktop / Cursor IDE)"]
        HttpMCP["MCP HTTP Router\n(POST /mcp/tools, GET /mcp/resources)"]
        RestAPI["FastAPI REST Endpoints\n(/api/auth, /api/risk, /api/analytics)"]
        Dashboard["React TypeScript Command Center\n(Dual-Lens Visualizations)"]
    end

    F1 & F2 & F3 --> ClientSanitizer
    ClientSanitizer --> ServerSanitizer
    F4 & F5 --> ServerSanitizer
    ServerSanitizer --> JobTable
    JobTable --> Worker
    Worker --> Parser
    Parser --> ReversalEngine
    ReversalEngine --> PaymentService
    PaymentService --> RiskService & DeclineDNA & LensDetector
    RiskService & DeclineDNA & LensDetector --> StdioMCP & HttpMCP & RestAPI & Dashboard
```

### 3.2 Real-Time Card Network Screening Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Cardholder
    participant Terminal as POS / ATM / Payment Gateway
    participant Network as Card Network (Mastercard / Visa)
    participant Sentinel as SaaS MCP Risk Sentinel
    participant Bank as Issuing Bank Core Banking System

    Cardholder->>Terminal: Initiates Transaction (₹2,500.00 at Swiggy)
    Terminal->>Network: Authorization Request (AuthReq)
    Network->>Sentinel: POST /api/risk/evaluate (<45ms SLA)
    Note over Sentinel: Evaluates Historical Entity Failure Rate,<br/>Rail Decline DNA & Card BIN Risk
    alt Risk Score < 60 (Normal Risk)
        Sentinel-->>Network: Decision: APPROVE (Route to clearing switch)
        Network->>Bank: Forward Authorization Request
        Bank-->>Network: Issuer Approved
        Network-->>Terminal: Approved (AuthCode: 441029)
    else Risk Score 60-84 (Elevated Risk)
        Sentinel-->>Network: Decision: REVIEW (Step-up 3DS / OTP Challenge)
        Network-->>Terminal: Challenge Cardholder
    else Risk Score >= 85 (Critical Anomaly)
        Sentinel-->>Network: Decision: DECLINE (Reason: HIGH_FAIL_ENTITY_VELOCITY)
        Network-->>Terminal: Declined (Suspected Rail / Terminal Outage)
    end
```

### 3.3 Automated Debit-Credit Reversal State Flow

```mermaid
stateDiagram-v2
    [*] --> OriginalDebit: Customer Swipes Card / ATM Withdrawal
    OriginalDebit --> DebitSettled: Bank Authorizes Debit (status: succeeded)
    DebitSettled --> ReversalDetected: Statement Upload (Credit with matching RRN or Entity+Amount)
    state ReversalDetected {
        [*] --> RRNMatch: Primary Exact Match on Reference No (RRN / UTR)
        RRNMatch --> FuzzyMatch: Secondary Fallback (Amount + Entity within 30 days)
    }
    ReversalDetected --> DebitFailed: Original Debit Flipped to FAILED (failure_code: RETURN_REVERSED)
    ReversalDetected --> CreditReturned: Reversal Credit Flipped to RETURNED
    DebitFailed --> AuditLogged: Bi-directional ReversalLink Stored (Tenant-Scoped)
    CreditReturned --> AuditLogged
    AuditLogged --> [*]
```

---

## 4. Model Context Protocol (MCP) Architecture

SaaS MCP implements a **dual-transport Model Context Protocol** interface compliant with the 2024-11-05 MCP specification:

```
                                  ┌──────────────────────────────┐
                                  │       SaaS MCP Server        │
                                  └──────────────┬───────────────┘
                                                 │
                     ┌───────────────────────────┴───────────────────────────┐
                     ▼                                                       ▼
        ┌─────────────────────────┐                             ┌─────────────────────────┐
        │   Stdio JSON-RPC 2.0    │                             │     FastAPI HTTP REST   │
        │   (app.mcp.cli)         │                             │     (/mcp/tools, etc.)  │
        └────────────┬────────────┘                             └────────────┬────────────┘
                     │                                                       │
         Claude Desktop / Cursor IDE                                 Web Agents / APIs
```

### 4.1 Stdio JSON-RPC 2.0 Server (`backend/app/mcp/cli.py`)
- **Transport**: Standard input/output (`sys.stdin` / `sys.stdout`) with newline-delimited JSON-RPC 2.0 messages.
- **Clean Logging**: All diagnostics, lifecycle info, and errors are routed strictly to `sys.stderr`, preserving stdout integrity for the JSON parser.
- **Authentication Resolution**:
  1. Resolves `SAAS_MCP_API_KEY` from the environment.
  2. Supports `--api-key <key>` CLI flag.
  3. In development mode (`APP_ENV != "production"`), automatically falls back to the database's primary organization with a logged notice.
- **Protocol Handshake**:
  - `initialize`: Returns protocolVersion (`2024-11-05`), capabilities (`tools: {}`, `resources: {}`), and serverInfo.
  - `notifications/initialized`: Acknowledged silently.
  - `ping`: Returns `{}`.
  - `tools/list`: Returns all 22 registered tools with typed `inputSchema`.
  - `tools/call`: Executes tool against service layer and returns formatted `{"content": [{"type": "text", "text": "..."}]}`.
  - `resources/list` & `resources/read`: Serves system and analytics context feeds.

### 4.2 Complete MCP Tool Catalog (22 Tools)

#### 1. System & Health (1 Tool)
| Tool Name | Parameters | Description |
|---|---|---|
| `health_check` | None | Returns backend status and service health. |

#### 2. Commerce Analytics & Storefronts (7 Tools)
| Tool Name | Parameters | Description |
|---|---|---|
| `list_commerce_sources` | None | Lists connected storefronts and commerce platforms. |
| `register_commerce_source` | `name`, `source`, `store_url` | Registers a new storefront or bank feed. |
| `ingest_canonical_commerce_event`| `storefront_id`, `event_name`, `payload` | Ingests a canonical commerce event (`purchase`, `refund`). |
| `get_analytics_summary` | `start_date`, `end_date` | Returns revenue, purchases, AOV, and customer KPIs. |
| `get_top_products` | `start_date`, `end_date`, `limit` | Surfaces best-performing SKUs by volume and revenue. |
| `get_customer_metrics` | `start_date`, `end_date` | Returns repeat customer rate and lifetime value metrics. |
| `get_refund_summary` | `start_date`, `end_date` | Returns total refunded amount, count, and refund rate. |

#### 3. Normalized Payments & Revenue Recovery (8 Tools)
| Tool Name | Parameters | Description |
|---|---|---|
| `get_payment_metrics` | `start_date`, `end_date` | Returns payment attempts, success rate, and succeeded/failed amounts. |
| `get_payment_failures` | `start_date`, `end_date`, `limit` | Returns failed attempts with failure reasons and recovery status. |
| `get_payment_recovery` | `start_date`, `end_date` | Returns recovered revenue and currently open recovery cases. |
| `get_revenue_at_risk` | None | Calculates currently unrecovered revenue across all open cases. |
| `get_customer_payment_history` | `customer_id` | Full chronological payment and recovery log for a customer. |
| `get_transaction_lifecycle` | `order_id` | Complete order lifecycle: order created $\to$ auth $\to$ capture $\to$ refund. |
| `get_revenue_metrics` | `start_date`, `end_date` | Gross vs net revenue accounting for chargebacks and fees. |
| `get_order_metrics` | `start_date`, `end_date` | Order completion rates and average basket size. |

#### 4. Card Switch, Risk & Statement Ingestion (6 Tools)
| Tool Name | Parameters | Description |
|---|---|---|
| `get_system_lens` | None | Returns the active surveillance perspective (`COMMERCE`, `BANK_NETWORK`, `HYBRID`). |
| `get_risk_assessment` | `start_date`, `end_date`, `channel` | Returns overall risk score, risk tier, highest risk channel, and phantom reversals. |
| `get_high_risk_entities` | `limit`, `min_failures`, `channel` | "Most Failed at Which Name" leaderboard ranking merchants and terminals. |
| `get_entity_risk_dna` | `entity_name` | Deep behavioral failure fingerprint across rails (ATM vs UPI vs POS). |
| `evaluate_transaction_risk` | `transaction_ref`, `entity_name`, `amount`, `channel`, `card_bin` | Sub-45ms real-time authorization risk assessment (`APPROVE`, `REVIEW`, `DECLINE`). |
| `ingest_statement_file` | `file_path`, `pdf_password` | Local filesystem bank statement ingestion (CSV, Excel, PDF) with PII masking and reversal linking. |

### 4.3 MCP System Resources
| Resource URI | MIME Type | Description |
|---|---|---|
| `system://info` | `application/json` | Server name, platform version, environment, and capabilities. |
| `analytics://summary` | `application/json` | Real-time organization revenue snapshot and payment success rate. |

---

## 5. Low-Level Design (LLD)

### 5.1 Universal Database Schema

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : owns
    ORGANIZATIONS ||--o{ API_KEYS : issues
    ORGANIZATIONS ||--o{ STOREFRONTS : configures
    ORGANIZATIONS ||--o{ IMPORT_BATCHES : uploads
    ORGANIZATIONS ||--o{ INGESTION_JOBS : executes
    STOREFRONTS ||--o{ COMMERCE_ORDERS : records
    STOREFRONTS ||--o{ PAYMENTS : lands
    COMMERCE_ORDERS ||--o{ ORDER_ITEMS : contains
    COMMERCE_ORDERS ||--o{ PAYMENTS : settles
    PAYMENTS ||--o{ PAYMENT_ATTEMPTS : tracks
    PAYMENTS ||--o{ RECOVERY_CASES : triggers
    PAYMENTS ||--o{ REVERSAL_LINKS : "original_debit"
    PAYMENTS ||--o{ REVERSAL_LINKS : "reversal_credit"

    ORGANIZATIONS {
        int id PK
        string name
        string slug
        datetime created_at
    }

    STOREFRONTS {
        int id PK
        int organization_id FK
        string name
        string provider
        string store_url
        string status
        string webhook_secret
        datetime created_at
    }

    PAYMENTS {
        int id PK
        int organization_id FK
        int storefront_id FK
        int order_id FK
        string payment_ref
        string status
        float amount
        string currency
        string channel
        string entity_name
        string raw_narration
        string direction
        string reference_no
        string failure_code
        int reversal_linked_id FK
        datetime occurred_at
    }

    REVERSAL_LINKS {
        int id PK
        int organization_id FK
        int original_payment_id FK
        int reversal_payment_id FK
        string match_type
        float amount
        string currency
        datetime linked_at
    }

    INGESTION_JOBS {
        int id PK
        int organization_id FK
        int storefront_id FK
        int import_batch_id FK
        string status
        int attempt_count
        string error_message
        json payload
        datetime created_at
        datetime updated_at
    }
```

### 5.2 Banking Narration Classifier & Extraction Pipeline
The normalization engine (`statement_parser.py`) executes a multi-stage classification pipeline:

```
[Raw Statement Narration]
           │
           ▼
[Stage 1: PII/PCI Masking]
   ├── 16-Digit Card Numbers  ──► [REDACTED_CARD_PAN]
   ├── Bank Account Numbers   ──► A/C [REDACTED_ACCT]
   ├── Aadhaar (12 digits)    ──► [REDACTED_AADHAAR]
   └── CVV Codes              ──► CVV [REDACTED_CVV]
           │
           ▼
[Stage 2: Reference Extraction] ── Extracts RRN (12 digits), UTR (16-22 chars), Cheque No
           │
           ▼
[Stage 3: Rail Channel Classifier]
   ├── "ATM WDL" / "NFS*ATM" / "MATM"       ──► ATM
   ├── "POS" / "EDC" / "SWIPE" / "CHIP"     ──► CARD_SWIPE
   ├── "UPI/" / "@upi" / "UPI-P2M"          ──► UPI
   ├── "ECOM" / "PG" / "RAZORPAY"           ──► ONLINE_CARD
   ├── "NEFT" / "RTGS" / "IMPS"             ──► TRANSFER
   └── Unmatched                            ──► OTHER
           │
           ▼
[Stage 4: Clean Entity Normalization]
   ├── "UPI/50291823/SWIGGY/ICICI"          ──► "Swiggy"
   ├── "ATM WDL CASH SBI KOTHRUD PUNE"      ──► "SBI ATM Kothrud Pune"
   ├── "POS SWIPE STARBUCKS PUNE IN"        ──► "Starbucks"
   └── "POS 401234xxxx AMAZON INDIA"        ──► "Amazon India"
           │
           ▼
[Stage 5: Reversal Detection]
   └── Matches ("REV", "REVERSAL", "REFUND", "RETURN", "FAILED TXN") ──► is_reversal = True
```

### 5.3 Risk Scoring & Decline DNA Formulas
The composite risk score for counterparties and ATM terminals is computed as:

$$\text{Risk Score} = \min\left(100, \; 40 \times F_{\text{rate}} + 30 \times \min\left(1, \frac{V_{\text{failed}}}{10000}\right) + 20 \times \min\left(1, \frac{N_{\text{failed}}}{10}\right) + 10 \times \Delta_{\text{reversal}}\right)$$

Where:
- $F_{\text{rate}}$: Historical failure rate percentage ($\frac{N_{\text{failed}}}{N_{\text{total}}}$).
- $V_{\text{failed}}$: Total financial volume lost to failed transactions.
- $N_{\text{failed}}$: Count of failed transactions.
- $\Delta_{\text{reversal}}$: Ratio of un-reconciled phantom reversals.

**Decision Thresholds for Real-Time Screening**:
- **Risk Score $< 60$**: `APPROVE` $\to$ Route immediately to card clearing switch.
- **Risk Score $60 - 84$**: `REVIEW` $\to$ Trigger step-up 3DS / OTP verification.
- **Risk Score $\ge 85$**: `DECLINE` $\to$ Decline auth request with reason `HIGH_FAIL_ENTITY_VELOCITY`.

---

## 6. Frontend Command Center & Surveillance Visualizations

The frontend dashboard (`frontend/`) is built with React 18, TypeScript, and Vite:

1. **Statement Cash Flow Trajectory**: Dual-flow interactive SVG chart tracking real deposits (credits) versus withdrawals (debits) over time.
2. **Banking Rail Risk Performance**: Side-by-side failure rate comparison across rails (ATM, UPI, POS, Online Card, Transfer).
3. **Denomination Ticket Size Distribution**: Histogram classifying transactions into Micro ($< 500$), Small ($500 - 2k$), Medium ($2k - 10k$), and Large ($> 10k$).
4. **Automated Reversal Reconciliation Panel**: Live dual-state tracking of paired RRN and UTR matches with settlement latency metrics.
5. **Entity Decline DNA Modal**: Drill-down inspection of specific merchants and terminals displaying multi-rail failure breakdown and actionable remediation guidance.
6. **Zero-Trust Import Wizard**: In-browser client-side PII scrubbing preview with instant token validation before file upload.

---

## 7. Installation, Configuration & Launch Guide

### 7.1 Backend Setup
```powershell
# 1. Activate Python virtual environment
backend\.venv\Scripts\Activate.ps1   # Windows
# source backend/.venv/bin/activate    # Linux/macOS

# 2. Run automated test suite (all 71 tests passing)
backend\.venv\Scripts\python.exe -m pytest

# 3. Launch FastAPI backend server
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 7.2 Frontend Setup
```powershell
cd frontend
npm install
npm run build   # Verifies TypeScript types and generates production bundle
npm run dev     # Starts Vite dev server at http://localhost:5173
```

### 7.3 Claude Desktop & Cursor IDE Configuration
To connect **Claude Desktop** or **Cursor IDE** directly to the SaaS MCP server:

```json
{
  "mcpServers": {
    "saas-mcp": {
      "command": "D:\\saas-mcp\\backend\\.venv\\Scripts\\python.exe",
      "args": ["-m", "app.mcp.cli"],
      "cwd": "D:\\saas-mcp\\backend",
      "env": {
        "SAAS_MCP_API_KEY": "YOUR_ORGANIZATION_API_KEY",
        "DATABASE_URL": "sqlite:///./saas_mcp.db"
      }
    }
  }
}
```

---

## 8. Security, Compliance & Production Hardening

### 8.1 Production Security Controls
- **PCI-DSS 3.4 & Privacy Compliance**: 16-digit card PANs, bank accounts, Aadhaar, and CVVs are permanently masked client-side and server-side.
- **Strict Multi-Tenant Scoping**: All database queries strictly filter by `organization_id == organization.id`. Cross-tenant data retrieval is structurally prevented.
- **Reverse Proxy Segmentation**: Restrict `/mcp/*` endpoints to loopback (`127.0.0.1`) or private VPCs; public clients connect via `/api/*`.
- **Production Environment (`.env.production`)**:
  ```ini
  APP_ENV=production
  DEBUG=false
  SECRET_KEY=<generate-high-entropy-jwt-secret>
  BOOTSTRAP_TOKEN=<generate-secure-bootstrap-token>
  API_KEY_PEPPER=<generate-secure-pepper>
  ALLOW_REGISTRATION=false
  DATABASE_URL=postgresql+psycopg2://user:password@host:5432/saas_mcp
  ```

### 8.2 Repository Cleanliness
To maintain security and clean version control, intermediate working documentation and internal folders are excluded from Git via `.gitignore`:
- Folders excluded: `skills/`, `agents/`, `tools/`, `docs/`.
- Files excluded: All `SECURITY*.md` and `RISK*.md` files.
- The single authoritative system design document is **`MASTER_SPECIFICATION.md`**.
