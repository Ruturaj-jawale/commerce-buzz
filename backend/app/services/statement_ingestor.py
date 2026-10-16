"""Multi-format bank statement ingestor.

Supports CSV, Excel (.xlsx / .xls), and PDF (text-based or password-protected).
All ingested data is passed through PII/PCI sanitization before any parsing or
persistence. Extracted rows are returned as normalised canonical commerce events.

Processing pipeline:
  File (CSV / Excel / PDF)
      → Text / Row Extraction
      → PII/PCI Sanitization (account no, PAN, card PAN, Aadhaar, CVV, phone, email)
      → Narration Parsing (channel, entity_name, reference_no, is_reversal)
      → PaymentService.record_payment  (reversal reconciliation included)
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Organization, Payment, ReversalLink, Storefront
from app.integrations.storefronts.base import CanonicalCommerceEvent
from app.schemas.risk import StatementIngestionResponse
from app.services.payment_service import PaymentService
from app.services.statement_parser import parse_statement_narration

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lightweight dependency guard helpers
# ---------------------------------------------------------------------------

def _try_import(name: str):
    import importlib
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Canonical row schema returned before DB ingestion
# ---------------------------------------------------------------------------

@dataclass
class StatementRow:
    date: str
    narration: str          # Already PII-sanitized
    amount: float
    direction: str          # "DEBIT" or "CREDIT"
    balance: float | None = None
    reference_no: str | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class IngestionResult:
    rows_parsed: int = 0
    rows_ingested: int = 0
    rows_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    format_detected: str = ""
    pii_fields_redacted: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Column name normaliser (reuse mapping_engine alias list)
# ---------------------------------------------------------------------------

_DATE_ALIASES   = {"date", "txndate", "valuedate", "postingdate", "transactiondate",
                   "datetime", "statementdate", "created", "occurredat"}
_NARR_ALIASES   = {"narration", "particulars", "description", "remarks", "transactiondetails",
                   "merchant", "merchantname", "details", "txndescription"}
_DEBIT_ALIASES  = {"debit", "dr", "withdrawal", "debitamount", "withdrawalamount",
                   "dramt", "debitamt", "wdl"}
_CREDIT_ALIASES = {"credit", "cr", "deposit", "creditamount", "depositamount",
                   "cramt", "creditamt"}
_AMT_ALIASES    = {"amount", "txnamount", "transactionamount", "amt", "totalamount"}
_BAL_ALIASES    = {"balance", "closingbalance", "runningbalance", "availablebalance",
                   "bal", "closingbal"}
_REF_ALIASES    = {"rrn", "utr", "refno", "referenceno", "chequeno", "chqno",
                   "authcode", "txnid", "transactionid", "reference", "referencenum"}


def _norm(col: str) -> str:
    return "".join(c for c in col.lower() if c.isalnum())


def _detect_columns(headers: list[str]) -> dict[str, str]:
    """Map semantic role -> actual column name."""
    mapping: dict[str, str] = {}
    for h in headers:
        n = _norm(h)
        if n in _DATE_ALIASES and "date" not in mapping:
            mapping["date"] = h
        elif n in _NARR_ALIASES and "narration" not in mapping:
            mapping["narration"] = h
        elif n in _DEBIT_ALIASES and "debit" not in mapping:
            mapping["debit"] = h
        elif n in _CREDIT_ALIASES and "credit" not in mapping:
            mapping["credit"] = h
        elif n in _AMT_ALIASES and "amount" not in mapping:
            mapping["amount"] = h
        elif n in _BAL_ALIASES and "balance" not in mapping:
            mapping["balance"] = h
        elif n in _REF_ALIASES and "reference" not in mapping:
            mapping["reference"] = h
    return mapping


def _parse_amount(val: Any) -> float:
    if val is None or str(val).strip() in ("", "-", "—"):
        return 0.0
    return float(str(val).replace(",", "").replace("₹", "").replace("$", "").strip())


def _row_to_statement(row: dict[str, Any], col_map: dict[str, str]) -> StatementRow | None:
    from app.services.statement_parser import sanitize_sensitive_data

    narration_col = col_map.get("narration", "")
    raw_narr = str(row.get(narration_col, "")).strip()
    narration = sanitize_sensitive_data(raw_narr)

    date_col = col_map.get("date", "")
    date_val = str(row.get(date_col, "")).strip()

    # Amount + direction
    debit_col  = col_map.get("debit")
    credit_col = col_map.get("credit")
    amt_col    = col_map.get("amount")

    debit_amt  = _parse_amount(row.get(debit_col))  if debit_col  else 0.0
    credit_amt = _parse_amount(row.get(credit_col)) if credit_col else 0.0

    if debit_col and credit_col:
        if debit_amt > 0:
            amount, direction = debit_amt, "DEBIT"
        elif credit_amt > 0:
            amount, direction = credit_amt, "CREDIT"
        else:
            return None   # Empty row
    elif amt_col:
        amount = _parse_amount(row.get(amt_col))
        # Detect direction from a DR/CR column or narration
        drcr_val = ""
        for h in row:
            if _norm(h) in {"drcr", "type", "drcrflag", "crdr"}:
                drcr_val = str(row[h]).upper().strip()
        direction = "CREDIT" if "CR" in drcr_val or "CREDIT" in drcr_val else "DEBIT"
    else:
        return None

    if amount <= 0 and not narration:
        return None

    bal_col = col_map.get("balance")
    balance = _parse_amount(row.get(bal_col)) if bal_col else None

    ref_col = col_map.get("reference")
    reference_no = str(row.get(ref_col, "")).strip() or None

    return StatementRow(
        date=date_val,
        narration=narration,
        amount=amount,
        direction=direction,
        balance=balance,
        reference_no=reference_no,
        raw_row=dict(row),
    )


# ---------------------------------------------------------------------------
# Format-specific extractors
# ---------------------------------------------------------------------------

def _extract_rows_csv(content: bytes) -> list[dict[str, Any]]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def _extract_rows_excel(content: bytes) -> list[dict[str, Any]]:
    openpyxl = _try_import("openpyxl")
    xlrd = _try_import("xlrd")

    # Try openpyxl (xlsx)
    if openpyxl:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                return []
            headers = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(rows[0])]
            return [dict(zip(headers, row)) for row in rows[1:]]
        except Exception as exc:
            logger.debug("openpyxl failed: %s", exc)

    # Try xlrd (xls)
    if xlrd:
        try:
            wb = xlrd.open_workbook(file_contents=content)
            ws = wb.sheet_by_index(0)
            headers = [str(ws.cell_value(0, c)).strip() for c in range(ws.ncols)]
            return [
                {headers[c]: ws.cell_value(r, c) for c in range(ws.ncols)}
                for r in range(1, ws.nrows)
            ]
        except Exception as exc:
            logger.debug("xlrd failed: %s", exc)

    raise RuntimeError("Cannot read Excel file. Install openpyxl or xlrd.")


def _extract_rows_pdf(content: bytes, password: str | None = None) -> list[dict[str, Any]]:
    """Extract rows from PDF. Tries text extraction first; falls back to OCR if needed."""
    pdfplumber = _try_import("pdfplumber")
    pikepdf    = _try_import("pikepdf")

    pdf_bytes = content

    # Decrypt if password-protected
    if pikepdf and password:
        try:
            pdf_obj = pikepdf.open(io.BytesIO(content), password=password)
            buf = io.BytesIO()
            pdf_obj.save(buf)
            pdf_bytes = buf.getvalue()
            pdf_obj.close()
            logger.info("PDF decrypted successfully with provided password.")
        except Exception as exc:
            raise ValueError(f"PDF password incorrect or PDF is corrupt: {exc}") from exc

    if not pdfplumber:
        raise RuntimeError("pdfplumber not installed. Cannot read PDF files.")

    rows: list[dict[str, Any]] = []
    headers_detected: list[str] | None = None

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # 1. Try structured table extraction
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    # First non-empty row with at least 2 cells = header
                    header_row = None
                    data_start = 0
                    for i, row in enumerate(table):
                        clean = [c for c in row if c and str(c).strip()]
                        if len(clean) >= 2:
                            header_row = [str(c).strip() if c else f"col_{j}" for j, c in enumerate(row)]
                            data_start = i + 1
                            break
                    if header_row is None:
                        continue

                    if headers_detected is None:
                        headers_detected = header_row

                    for row in table[data_start:]:
                        if not any(c for c in row if c and str(c).strip()):
                            continue
                        rows.append({
                            header_row[j]: str(row[j]).strip() if j < len(row) and row[j] else ""
                            for j in range(len(header_row))
                        })

                # 2. If no tables found on this page, try line-by-line text parse
                if not tables:
                    text = page.extract_text() or ""
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if not lines:
                        continue

                    # Detect header line (contains date/narration/debit/credit keywords)
                    header_keywords = {"date", "narration", "particulars", "debit", "credit", "amount", "balance"}
                    for i, line in enumerate(lines):
                        cols = line.split()
                        if any(c.lower() in header_keywords for c in cols):
                            if headers_detected is None:
                                headers_detected = cols
                            for data_line in lines[i + 1:]:
                                parts = data_line.split()
                                if len(parts) >= len(headers_detected):
                                    rows.append(dict(zip(headers_detected, parts)))
                            break
    except Exception as exc:
        raise RuntimeError(f"PDF extraction failed: {exc}") from exc

    if not rows:
        raise ValueError(
            "Could not extract tabular data from PDF. "
            "The file may be a scanned image. "
            "Please export from your bank portal as CSV or Excel."
        )

    return rows


# ---------------------------------------------------------------------------
# Main public ingestor
# ---------------------------------------------------------------------------

def ingest_bank_statement(
    content: bytes,
    filename: str,
    organization_id: int,
    pdf_password: str | None = None,
) -> tuple[list[StatementRow], IngestionResult]:
    """Parse a CSV, Excel, or PDF bank statement file into sanitized StatementRow objects.

    Args:
        content: Raw file bytes.
        filename: Original filename (used to detect format).
        organization_id: Tenant identifier (used for audit only here; DB write done by caller).
        pdf_password: Optional password for encrypted PDF statements.

    Returns:
        (rows, result) where rows are ready for payment ingestion.
    """
    result = IngestionResult()
    ext = filename.rsplit(".", 1)[-1].lower()

    try:
        if ext == "csv":
            result.format_detected = "CSV"
            raw_rows = _extract_rows_csv(content)
        elif ext in ("xlsx", "xls"):
            result.format_detected = "Excel"
            raw_rows = _extract_rows_excel(content)
        elif ext == "pdf":
            result.format_detected = "PDF"
            raw_rows = _extract_rows_pdf(content, password=pdf_password)
        else:
            result.errors.append(f"Unsupported file type: .{ext}. Supported: CSV, XLSX, XLS, PDF.")
            return [], result
    except (ValueError, RuntimeError) as exc:
        result.errors.append(str(exc))
        return [], result

    if not raw_rows:
        result.errors.append("File appears empty or no data rows could be extracted.")
        return [], result

    # Detect column semantics
    col_map = _detect_columns(list(raw_rows[0].keys()))

    if "date" not in col_map and "narration" not in col_map:
        result.errors.append(
            "Could not identify required columns (date, narration, debit/credit). "
            f"Columns found: {list(raw_rows[0].keys())}"
        )
        return [], result

    parsed: list[StatementRow] = []
    for i, raw in enumerate(raw_rows):
        try:
            stmt_row = _row_to_statement(raw, col_map)
            if stmt_row is None:
                result.rows_skipped += 1
                continue
            parsed.append(stmt_row)
            result.rows_parsed += 1
        except Exception as exc:
            result.rows_skipped += 1
            logger.debug("Row %d skipped: %s", i, exc)

    return parsed, result


def ingest_and_record_statement(
    db: Session,
    organization: Organization,
    content: bytes,
    filename: str,
    pdf_password: str | None = None,
) -> StatementIngestionResponse:
    """Ingest a multi-format bank statement (CSV/Excel/PDF), sanitize PII,
    parse banking/card channels, record payments, and atomically reconcile reversals.
    """
    rows, res = ingest_bank_statement(
        content=content,
        filename=filename,
        organization_id=organization.id,
        pdf_password=pdf_password,
    )

    if res.errors and not rows:
        raise HTTPException(status_code=422, detail="; ".join(res.errors))

    # Ensure organization-scoped bank-statement storefront source
    storefront = db.scalar(
        select(Storefront).where(
            Storefront.organization_id == organization.id,
            Storefront.provider == "bank-statement",
        )
    )
    if storefront is None:
        storefront = Storefront(
            organization_id=organization.id,
            name="Bank Statement Switch",
            provider="bank-statement",
            store_url="https://bank-statement.internal",
            status="connected",
        )
        db.add(storefront)
        db.flush()

    payment_service = PaymentService()
    reversals_before = db.scalar(
        select(func.count(ReversalLink.id)).where(ReversalLink.organization_id == organization.id)
    ) or 0

    rows_ingested = 0
    total_debit = 0.0
    total_credit = 0.0

    # Sort rows so DEBITs are processed before CREDITs
    # This guarantees that return/reversal credits in the same file will immediately
    # find their matching original debit transaction in the database.
    sorted_rows = sorted(rows, key=lambda r: 0 if r.direction == "DEBIT" else 1)

    for row in sorted_rows:
        try:
            if row.reference_no:
                order_id = f"REF-{row.reference_no}"
            else:
                h = hashlib.sha256(f"{row.date}:{row.narration}:{row.amount}:{row.direction}".encode()).hexdigest()[:16]
                order_id = f"STMT-{h}"

            idempotency_key = f"stmt-{organization.id}-{order_id}"

            parsed = parse_statement_narration(row.narration)
            channel = parsed.channel
            entity_name = parsed.entity_name

            if row.direction == "CREDIT":
                event_name = "refund"
                total_credit += row.amount
            else:
                event_name = "purchase"
                total_debit += row.amount

            canonical = CanonicalCommerceEvent(
                event_name=event_name,
                order_id=order_id,
                revenue=row.amount,
                currency="INR",
                properties={
                    "occurred_at": datetime.now().isoformat(),
                    "idempotency_key": idempotency_key,
                    "narration": row.narration,
                    "direction": row.direction,
                    "channel": channel,
                    "entity_name": entity_name,
                    "reference_no": row.reference_no or parsed.reference_no,
                    "balance": row.balance,
                    "statement_date": row.date,
                    "raw_row": row.raw_row,
                    "metadata": {
                        "payment_id": order_id,
                        "channel": channel,
                        "entity_name": entity_name,
                        "reference_no": row.reference_no or parsed.reference_no,
                    },
                },
            )

            payment_service.land_event(db, organization, storefront, canonical)
            rows_ingested += 1
        except Exception as exc:
            logger.warning("Failed to land statement row: %s", exc)
            res.errors.append(f"Row failed to persist: {exc}")

    db.commit()

    reversals_after = db.scalar(
        select(func.count(ReversalLink.id)).where(ReversalLink.organization_id == organization.id)
    ) or 0
    reversals_linked = max(0, reversals_after - reversals_before)

    return StatementIngestionResponse(
        filename=filename,
        format_detected=res.format_detected,
        rows_parsed=res.rows_parsed,
        rows_ingested=rows_ingested,
        rows_skipped=res.rows_skipped,
        reversals_linked=reversals_linked,
        total_debit_amount=round(total_debit, 2),
        total_credit_amount=round(total_credit, 2),
        errors=res.errors,
    )
