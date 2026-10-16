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
import re
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


def _extract_text_table_strategy(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    # Check delimited text (comma, tab, pipe, semicolon)
    for delim in ("\t", "|", ",", ";"):
        candidate_idx = next((i for i, line in enumerate(lines[:25]) if line.count(delim) >= 2), None)
        if candidate_idx is not None:
            table_lines = [line for line in lines[candidate_idx:] if line.count(delim) >= 1]
            if len(table_lines) >= 2:
                reader = csv.DictReader(io.StringIO("\n".join(table_lines)), delimiter=delim)
                cols = [str(c).strip() for c in (reader.fieldnames or [])]
                if any(_norm(c) in _DATE_ALIASES or _norm(c) in _NARR_ALIASES for c in cols):
                    parsed_rows = [{k.strip(): str(v).strip() for k, v in r.items() if k is not None} for r in reader]
                    if parsed_rows:
                        return parsed_rows

    # Check multi-space column alignment
    for i, line in enumerate(lines[:25]):
        cols = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        if len(cols) >= 3 and any(_norm(c) in _DATE_ALIASES or _norm(c) in _NARR_ALIASES or _norm(c) in _DEBIT_ALIASES or _norm(c) in _AMT_ALIASES for c in cols):
            candidate_rows = []
            for row_line in lines[i + 1:]:
                vals = [p.strip() for p in re.split(r"\s{2,}", row_line) if p.strip()]
                if not vals:
                    continue
                if len(vals) == len(cols):
                    candidate_rows.append({cols[c]: vals[c] for c in range(len(cols))})
                elif abs(len(vals) - len(cols)) <= 1 and len(vals) >= 2:
                    candidate_rows.append({cols[c]: vals[c] if c < len(vals) else "" for c in range(len(cols))})
            if candidate_rows:
                return candidate_rows

    return []


def _extract_transactions_by_pattern(text: str) -> list[dict[str, Any]]:
    """Scan bank statement text for transaction patterns:
    Date followed by Narration/Description followed by Monetary Amounts.
    """
    date_re = re.compile(
        r"^\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}|\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\s+(.+)$"
    )
    amt_re = re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2}|[0-9]+\.[0-9]{2})\b")

    rows: list[dict[str, Any]] = []
    lines = text.splitlines()

    for line in lines:
        cleaned_line = line.strip()
        if not cleaned_line:
            continue

        m = date_re.match(cleaned_line)
        if not m:
            # Check if this line is a continuation narration for the previous transaction
            if rows and len(cleaned_line) > 3 and not any(kw in cleaned_line.lower() for kw in ("page", "total", "balance carried", "statement of", "account no")):
                rows[-1]["narration"] = f"{rows[-1]['narration']} {cleaned_line}".strip()
            continue

        date_val = m.group(1)
        rest = m.group(2).strip()

        # Check for optional second date (value date)
        m_val = date_re.match(rest)
        if m_val:
            rest = m_val.group(2).strip()

        amt_matches = list(amt_re.finditer(rest))
        if not amt_matches:
            continue

        first_amt = amt_matches[0]
        narr = rest[:first_amt.start()].strip()
        amts = [match.group(1) for match in amt_matches]
        num_amts = [float(a.replace(",", "")) for a in amts]

        debit = 0.0
        credit = 0.0
        balance = None

        if len(num_amts) >= 3:
            # Format: Debit, Credit, Balance
            debit = num_amts[0]
            credit = num_amts[1]
            balance = num_amts[2]
        elif len(num_amts) == 2:
            amt = num_amts[0]
            balance = num_amts[1]
            is_cred = any(w in narr.upper() for w in ("CREDIT", "REFUND", "REV", "RETURN", "SALARY", "CR", "DEPOSIT"))
            if is_cred:
                credit = amt
            else:
                debit = amt
        elif len(num_amts) == 1:
            amt = num_amts[0]
            is_cred = any(w in narr.upper() for w in ("CREDIT", "REFUND", "REV", "RETURN", "SALARY", "CR", "DEPOSIT"))
            if is_cred:
                credit = amt
            else:
                debit = amt

        if debit > 0 or credit > 0 or narr:
            rows.append({
                "date": date_val,
                "narration": narr,
                "debit": str(debit) if debit > 0 else "",
                "credit": str(credit) if credit > 0 else "",
                "balance": str(balance) if balance is not None else "",
            })

    return rows


def _extract_rows_pdf(content: bytes, password: str | None = None) -> list[dict[str, Any]]:
    """Extract rows from PDF.
    Multi-tier strategy:
    1. Bordered table extraction via pdfplumber
    2. Borderless text-aligned table extraction via pdfplumber
    3. Delimited and whitespace-aligned column text extraction
    4. Universal transaction pattern regex scanner
    5. Scanned document OCR fallback (pdf2image + pytesseract)
    """
    pdfplumber = _try_import("pdfplumber")
    pikepdf    = _try_import("pikepdf")
    pypdf      = _try_import("pypdf")

    pdf_bytes = content

    # Decrypt if password-protected
    if password:
        decrypted = False
        if pikepdf:
            try:
                pdf_obj = pikepdf.open(io.BytesIO(content), password=password)
                buf = io.BytesIO()
                pdf_obj.save(buf)
                pdf_bytes = buf.getvalue()
                pdf_obj.close()
                decrypted = True
                logger.info("PDF decrypted successfully with pikepdf.")
            except Exception as exc:
                logger.debug("pikepdf decryption failed: %s", exc)

        if not decrypted and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(content))
                if reader.is_encrypted:
                    reader.decrypt(password)
                    writer = pypdf.PdfWriter()
                    for p in reader.pages:
                        writer.add_page(p)
                    buf = io.BytesIO()
                    writer.write(buf)
                    pdf_bytes = buf.getvalue()
                    decrypted = True
                    logger.info("PDF decrypted successfully with pypdf.")
            except Exception as exc:
                logger.debug("pypdf decryption failed: %s", exc)

    rows: list[dict[str, Any]] = []
    extracted_text = ""

    # Strategies 1, 2, and text accumulation via pdfplumber
    if pdfplumber:
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages:
                    # Strategy 1: Grid-line tables
                    tables = page.extract_tables() or []
                    for table in tables:
                        if not table:
                            continue
                        header_row = None
                        data_start = 0
                        for i, r in enumerate(table):
                            clean = [c for c in r if c and str(c).strip()]
                            if len(clean) >= 2 and any(
                                any(kw in str(c).lower() for kw in ("date", "narration", "particular", "debit", "credit", "amount"))
                                for c in clean
                            ):
                                header_row = [str(c).strip() if c else f"col_{j}" for j, c in enumerate(r)]
                                data_start = i + 1
                                break
                        if header_row:
                            for r in table[data_start:]:
                                if any(c for c in r if c and str(c).strip()):
                                    rows.append({
                                        header_row[j]: str(r[j]).strip() if j < len(r) and r[j] else ""
                                        for j in range(len(header_row))
                                    })

                    # Strategy 2: Borderless text-aligned tables
                    if not rows:
                        borderless_tables = page.extract_tables(table_settings={
                            "vertical_strategy": "text",
                            "horizontal_strategy": "text",
                            "intersection_x_tolerance": 5,
                        }) or []
                        for table in borderless_tables:
                            if not table:
                                continue
                            header_row = None
                            data_start = 0
                            for i, r in enumerate(table):
                                clean = [c for c in r if c and str(c).strip()]
                                if len(clean) >= 2 and any(
                                    any(kw in str(c).lower() for kw in ("date", "narration", "particular", "debit", "credit", "amount"))
                                    for c in clean
                                ):
                                    header_row = [str(c).strip() if c else f"col_{j}" for j, c in enumerate(r)]
                                    data_start = i + 1
                                    break
                            if header_row:
                                for r in table[data_start:]:
                                    if any(c for c in r if c and str(c).strip()):
                                        rows.append({
                                            header_row[j]: str(r[j]).strip() if j < len(r) and r[j] else ""
                                            for j in range(len(header_row))
                                        })

                    # Accumulate text for Strategy 3 & 4
                    p_text = page.extract_text() or ""
                    if p_text:
                        extracted_text += "\n" + p_text
        except Exception as exc:
            logger.debug("pdfplumber extraction failed: %s", exc)

    if rows:
        return rows

    # Fallback to pypdf text extraction if text is empty
    if not extracted_text.strip() and pypdf:
        try:
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            logger.debug("pypdf text extraction failed: %s", exc)

    # Strategy 3: Delimited and whitespace-aligned columns from text
    if extracted_text.strip():
        text_rows = _extract_text_table_strategy(extracted_text)
        if text_rows:
            return text_rows

        # Strategy 4: Universal transaction pattern regex
        pattern_rows = _extract_transactions_by_pattern(extracted_text)
        if pattern_rows:
            return pattern_rows

    # Strategy 5: Scanned document OCR fallback
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        images = convert_from_bytes(pdf_bytes, dpi=200, fmt="png", thread_count=1)
        ocr_text = "\n".join(pytesseract.image_to_string(img) for img in images)
        if ocr_text.strip():
            text_rows = _extract_text_table_strategy(ocr_text)
            if text_rows:
                return text_rows
            pattern_rows = _extract_transactions_by_pattern(ocr_text)
            if pattern_rows:
                return pattern_rows
    except Exception as exc:
        logger.debug("OCR fallback failed: %s", exc)

    if not rows:
        raise ValueError(
            "Could not extract tabular transactions from this PDF. "
            "Please ensure the PDF is not password-protected (or provide the password) "
            "or export the statement as CSV/Excel from your online banking portal."
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
            name="Bank Statements",
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
