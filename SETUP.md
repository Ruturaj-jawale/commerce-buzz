# SaaS MCP — Complete Setup & Installation Guide

This guide covers everything required to install, configure, verify, and run the **SaaS MCP** platform across backend services, frontend dashboard, and the Model Context Protocol (MCP) server.

---

## 1. System Prerequisites

| Component | Minimum Version | Recommended | Notes |
|---|---|---|---|
| **Python** | 3.11+ | 3.12.x | Required for FastAPI backend and MCP tools |
| **Node.js** | 18.x | 20.x+ | Required for React TypeScript dashboard |
| **npm** | 9.x+ | 10.x+ | Package manager for frontend |
| **Database** | SQLite (built-in) | PostgreSQL 15+ | Zero-config SQLite out of the box |
| **Operating System** | Windows, macOS, Linux | Any modern 64-bit OS | Fully cross-platform |

---

## 2. Quickstart (5-Minute Local Launch)

```powershell
# 1. Clone repository
git clone <repo-url> saas-mcp
cd saas-mcp

# 2. Activate Python Virtual Environment
backend\.venv\Scripts\Activate.ps1   # On Windows
# source backend/.venv/bin/activate    # On Linux/macOS

# 3. Install Python Dependencies
pip install -r backend/requirements.txt

# 4. Verify Backend Health (Runs all 69 automated tests)
pytest

# 5. Start Backend API & MCP Server
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

# 6. In a new terminal, build & launch Frontend Dashboard
cd frontend
npm install
npm run dev
```

Visit the dashboard at `http://localhost:5173`. The backend API and interactive docs are available at `http://127.0.0.1:8000/docs`.

---

## 3. Backend Setup & Configuration

### 3.1 Directory Structure
```
backend/
├── app/
│   ├── api/routes/          # HTTP REST endpoints (auth, risk, imports, webhooks)
│   ├── core/                # Settings, security, and configuration
│   ├── db/                  # SQLAlchemy models and database session management
│   ├── integrations/        # Commerce and provider adapters (Shopify, Stripe, etc.)
│   ├── mcp/                 # Model Context Protocol tools, resources, and CLI
│   │   ├── tools/           # commerce_tools.py, payment_tools.py, risk_tools.py
│   │   └── resources/       # analytics_resource.py, system_resource.py
│   ├── schemas/             # Pydantic request/response schemas
│   └── services/            # Core business logic (risk, payment, statement ingestor)
├── requirements.txt         # Production & testing Python dependencies
└── pytest.ini               # Test configuration
```

### 3.2 Environment Variables (`.env`)
Create a `.env` file in the project root or configure these environment variables:

```ini
# Application Configuration
APP_ENV=development
DEBUG=true
PORT=8000
HOST=127.0.0.1

# Security & Secret Keys
SECRET_KEY=change-this-to-a-secure-random-secret-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALLOWED_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Database Connection
# Default: SQLite database created automatically at backend/saas_mcp.db
DATABASE_URL=sqlite:///./backend/saas_mcp.db
# PostgreSQL Example:
# DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/saas_mcp

# MCP Server Settings
MCP_SERVER_NAME=saas-mcp
MCP_SERVER_VERSION=0.1.0

# Rate Limiting & File Upload Limits
MAX_IMPORT_FILE_BYTES=52428800    # 50 MB
MAX_IMPORT_ROWS=50000
```

### 3.3 Database Auto-Migration
The backend automatically creates tables and verifies schema alignment on startup via `init_db()` in `app/db/database.py`. No manual Alembic migration step is required for standard deployment.

---

## 4. Frontend Setup & Build

### 4.1 Development Server
```powershell
cd frontend
npm install
npm run dev
```
The Vite development server hot-reloads on edits and proxies API calls to `http://127.0.0.1:8000`.

### 4.2 Production Compilation
```powershell
npm run build
```
This runs TypeScript type-checking (`tsc --noEmit`) and Vite chunk packaging. The production artifacts are generated in `frontend/dist/`.

---

## 5. Model Context Protocol (MCP) Setup

SaaS MCP provides in-process and CLI-callable MCP servers compatible with **Claude Desktop**, **Cursor IDE**, and custom autonomous AI agents.

### 5.1 Claude Desktop Configuration
Add the following snippet to your `claude_desktop_config.json`:

* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Linux**: `~/.config/Claude/claude_desktop_config.json`

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

### 5.2 Cursor IDE Configuration
In Cursor IDE:
1. Open **Settings** $\to$ **Features** $\to$ **MCP Servers**.
2. Click **Add New MCP Server**.
3. Set Name to `saas-mcp`.
4. Set Type to `command`.
5. Enter command: `D:\saas-mcp\backend\.venv\Scripts\python.exe -m app.mcp.cli`.
6. Add environment variable `SAAS_MCP_API_KEY`.

---

## 6. Multi-Vector Ingestion Setup

The platform natively ingests data across five primary channels:

| Ingestion Channel | Supported Formats | Required Libraries | Ingestion Mechanism |
|---|---|---|---|
| **Excel** | `.xlsx`, `.xls` | `openpyxl`, `xlrd` | Pre-parsed into canonical commerce rows with debit/credit column auto-mapping. |
| **API** | JSON payloads, multipart uploads | Built-in FastAPI | `POST /api/analytics/statements/upload`, `POST /api/imports/file`, `POST /api/risk/evaluate`. |
| **MCP** | Local file paths via LLM | In-process dispatch | `ingest_statement_file(file_path, pdf_password)` callable directly by AI agents. |
| **PDF** | Text and password-encrypted `.pdf` | `pdfplumber`, `pypdf`, `pikepdf` | Decrypted with provided password, tables extracted, and zero-trust sanitized. |
| **CSV** | Plain `.csv`, `.txt` | Standard library `csv` | Pre-transport client sanitization + server normalization. |

All necessary libraries (`openpyxl`, `xlrd`, `pdfplumber`, `pypdf`, `pikepdf`, `tesseract.js`) are pre-configured in `backend/requirements.txt` and `frontend/package.json`.

---

## 7. Zero-Trust PII & PCI Sanitization Architecture

To ensure strict compliance with **PCI-DSS 3.4**, **GDPR**, and global privacy regulations, sensitive banking and cardholder data is sanitized at two independent boundaries:

1. **Client-Side Pre-Transport Boundary** (`frontend/src/utils/sanitizer.ts`):
   * When a statement is selected in the browser, card PANs (16 digits), bank account numbers, Aadhaar IDs, and CVVs are masked in browser memory.
   * Plaintext personal data never leaves the user's computer.
2. **Server-Side Ingestion Gatekeeper** (`backend/app/services/statement_parser.py`):
   * Inspects all incoming payloads before database persistence.
   * Preserves reconciliation tokens (RRN, UTR, Cheque No) using smart placeholder tokenization so automated debit-credit reversal linking remains functional.

---

## 8. Verification & Test Suite Execution

Run the complete backend test suite to verify tenant isolation, statement parsing, risk algorithms, and MCP tools:

```powershell
# Run all tests
pytest

# Run risk, statement ingestion, and reversal reconciliation suites
pytest tests/backend/test_statement_ingestor.py tests/backend/test_risk.py tests/backend/test_reversals.py

# Run with verbose output
pytest -v
```

All 69 automated test suites must pass before deploying to staging or production.

---

## 9. Troubleshooting & FAQ

#### Q: `pytest` command not recognized in PowerShell.
**Solution**: Make sure you have activated the virtual environment:
```powershell
backend\.venv\Scripts\Activate.ps1
# Or run directly via path:
backend\.venv\Scripts\pytest
```

#### Q: PDF statement returns password error.
**Solution**: Bank statements from SBI, HDFC, or ICICI often require a password (typically Date of Birth `DDMMYYYY` or last 4 digits of account/mobile). Pass the password in the frontend upload dialog or via `pdf_password` in the MCP tool.

#### Q: How is multi-tenant isolation enforced?
**Solution**: Every database query and service method requires an authenticated `Organization` context. Data queries strictly filter by `organization_id == organization.id`.
