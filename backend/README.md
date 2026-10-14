# Backend

FastAPI application with SQLAlchemy and an isolated MCP server.

## PowerShell

```powershell
D:
cd D:\saas-mcp\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health: http://127.0.0.1:8000/health

## File imports

The import API accepts `.csv`, `.xlsx`, and `.pdf` transaction exports. PDFs
with selectable delimited text (tab, pipe, comma, or semicolon) work by default.
For scanned PDFs, set `PDF_OCR_ENABLED=true` and install Tesseract OCR plus
Poppler on the backend host/container. OCR is intentionally disabled by default
because it is CPU-intensive and processes untrusted uploads.
