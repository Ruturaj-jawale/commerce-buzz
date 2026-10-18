"""CSV, Excel, and selectable-text PDF import workflow."""

import csv
import io
import json
import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ImportBatch, IngestionJob, Organization
from app.schemas.analytics import CommerceEventIngest
from app.schemas.imports import (
    ImportBatchRead,
    ImportCreated,
    ImportJobError,
    ImportStatusRead,
    ValidationIssue,
    ValidationReport,
)
from app.schemas.storefront import StorefrontCreateRequest
from app.services import mapping_engine
from app.services.ingestion_job_service import IngestionJobService
from app.services.storefront_service import StorefrontService

PREVIEW_SAMPLE_ROWS = 10
MAX_JOB_ERRORS = 50


class ImportService:
    def __init__(self) -> None:
        self._sources = StorefrontService()
        self._jobs = IngestionJobService()

    def create_upload(self, db: Session, organization: Organization, storefront_id: int, filename: str, content: bytes) -> ImportCreated:
        self._sources.get(db, organization, storefront_id)
        settings = get_settings()
        if len(content) > settings.max_import_file_bytes:
            raise HTTPException(status_code=413, detail="Import file exceeds the configured maximum size")
        safe_name = (filename or "upload").rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:255] or "upload"
        kind = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
        if kind == "csv":
            columns, rows = _parse_csv(content)
        elif kind == "xlsx":
            columns, rows = _parse_xlsx(content)
        elif kind == "pdf":
            columns, rows = _parse_pdf(content)
        elif kind in {"png", "jpg", "jpeg", "webp", "bmp", "tiff"}:
            columns, rows = _parse_image(content, safe_name)
        else:
            raise HTTPException(status_code=422, detail="Unsupported file type. Upload a .csv, .xlsx, .pdf, or image (.png, .jpg, .jpeg, .webp).")
        if not columns:
            raise HTTPException(status_code=422, detail="The file has no header row")
        if len(columns) > 200:
            raise HTTPException(status_code=422, detail="The file has too many columns (maximum 200)")
        if not rows:
            raise HTTPException(status_code=422, detail="The file has no data rows")
        if len(rows) > settings.max_import_rows:
            raise HTTPException(status_code=422, detail=f"The file has {len(rows)} rows; the maximum is {settings.max_import_rows}")

        batch = ImportBatch(
            organization_id=organization.id,
            storefront_id=storefront_id,
            filename=safe_name,
            file_kind=kind,
            status="uploaded",
            columns_json=json.dumps(columns),
            rows_json=json.dumps(rows),
            total_rows=len(rows),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return ImportCreated(
            batch=self._to_read(db, batch),
            sample_rows=rows[:PREVIEW_SAMPLE_ROWS],
            suggested_mapping=mapping_engine.suggest_mapping(columns),
        )

    def create_upload_without_source(
        self, db: Session, organization: Organization, filename: str, content: bytes,
        source_name: str | None = None, source_label: str | None = None,
    ) -> ImportCreated:
        """Create a tenant-local file source only when the upload has no selected source."""
        clean_name = (source_name or "File import").strip() or "File import"
        clean_label = (source_label or "file-import").strip() or "file-import"
        source = self._sources.connect(
            db,
            organization,
            StorefrontCreateRequest(
                name=clean_name[:120],
                source=clean_label[:80],
                store_url="https://file-import.invalid",
            ),
        )
        return self.create_upload(db, organization, source.id, filename, content)

    def set_mapping(self, db: Session, organization: Organization, batch_id: int, mapping: dict[str, Any]) -> ValidationReport:
        batch = self._get_owned(db, organization, batch_id)
        columns = json.loads(batch.columns_json)
        errors = mapping_engine.validate_mapping(mapping, columns)
        if errors:
            raise HTTPException(status_code=422, detail="; ".join(errors))
        rows = json.loads(batch.rows_json)
        events, issues = mapping_engine.build_events(rows, mapping)

        batch.mapping_json = json.dumps(mapping)
        batch.valid_rows = len(events)
        batch.invalid_rows = len({issue["row"] for issue in issues})
        batch.issues_json = json.dumps(issues[: mapping_engine.MAX_ISSUES_STORED])
        batch.status = "validated"
        db.commit()
        db.refresh(batch)
        return ValidationReport(
            total_rows=batch.total_rows,
            valid_rows=batch.valid_rows,
            invalid_rows=batch.invalid_rows,
            issues=[ValidationIssue(**issue) for issue in issues[: mapping_engine.MAX_ISSUES_STORED]],
            preview_payloads=[event["payload"] for event in events[:3]],
        )

    def start_import(self, db: Session, organization: Organization, batch_id: int) -> ImportBatchRead:
        batch = self._get_owned(db, organization, batch_id)
        if batch.status not in {"validated", "completed", "failed"}:
            raise HTTPException(status_code=422, detail="Set and validate a column mapping before importing")
        if batch.mapping_json is None:
            raise HTTPException(status_code=422, detail="Set and validate a column mapping before importing")
        mapping = json.loads(batch.mapping_json)
        rows = json.loads(batch.rows_json)
        events, _ = mapping_engine.build_events(rows, mapping)
        if not events:
            raise HTTPException(status_code=422, detail="No valid rows to import; fix the mapping or the file")

        for event in events:
            body = event["payload"]
            inner = body["payload"]
            inner["metadata"] = {**inner.get("metadata", {}), "import_batch_id": batch.id}
            ingest = CommerceEventIngest(event_name=body["event_name"], payload=inner)
            self._jobs.enqueue(
                db,
                organization,
                batch.storefront_id,
                ingest,
                import_batch_id=batch.id,
                source_row=event["source_row"],
            )
        batch.status = "importing"
        db.commit()
        db.refresh(batch)
        return self._to_read(db, batch)

    def get_status(self, db: Session, organization: Organization, batch_id: int) -> ImportStatusRead:
        batch = self._get_owned(db, organization, batch_id)
        read = self._to_read(db, batch)
        issues = [ValidationIssue(**issue) for issue in json.loads(batch.issues_json)]
        failed_jobs = db.scalars(
            select(IngestionJob)
            .where(IngestionJob.import_batch_id == batch.id, IngestionJob.status == "failed")
            .order_by(IngestionJob.id)
            .limit(MAX_JOB_ERRORS)
        ).all()
        return ImportStatusRead(
            batch=read,
            issues=issues,
            job_errors=[
                ImportJobError(job_id=job.id, source_row=job.source_row, message=job.error_message)
                for job in failed_jobs
            ],
        )

    def list_batches(self, db: Session, organization: Organization) -> list[ImportBatchRead]:
        batches = db.scalars(
            select(ImportBatch).where(ImportBatch.organization_id == organization.id).order_by(ImportBatch.id.desc()).limit(50)
        ).all()
        return [self._to_read(db, batch) for batch in batches]

    def _get_owned(self, db: Session, organization: Organization, batch_id: int) -> ImportBatch:
        batch = db.get(ImportBatch, batch_id)
        if batch is None or batch.organization_id != organization.id:
            raise HTTPException(status_code=404, detail="Import not found")
        return batch

    def _to_read(self, db: Session, batch: ImportBatch) -> ImportBatchRead:
        counts = dict(
            db.execute(
                select(IngestionJob.status, func.count())
                .where(IngestionJob.import_batch_id == batch.id)
                .group_by(IngestionJob.status)
            ).all()
        )
        queued = counts.get("queued", 0)
        processing = counts.get("processing", 0)
        completed = counts.get("completed", 0)
        failed = counts.get("failed", 0)
        if batch.status == "importing" and queued + processing == 0:
            batch.status = "completed" if failed == 0 else "failed"
            db.commit()
            db.refresh(batch)
        return ImportBatchRead(
            id=batch.id,
            storefront_id=batch.storefront_id,
            filename=batch.filename,
            file_kind=batch.file_kind,
            status=batch.status,
            columns=json.loads(batch.columns_json),
            total_rows=batch.total_rows,
            valid_rows=batch.valid_rows,
            invalid_rows=batch.invalid_rows,
            queued_jobs=queued,
            processing_jobs=processing,
            completed_jobs=completed,
            failed_jobs=failed,
            mapping=json.loads(batch.mapping_json) if batch.mapping_json else None,
            created_at=batch.created_at,
        )


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


_COMMON_IMPORT_KEYWORDS = {
    "date", "time", "id", "name", "amount", "revenue", "total", "price",
    "status", "txn", "trans", "particular", "particulars", "narration",
    "debit", "credit", "withdrwal", "withdrawal", "deposit", "balance",
    "ref", "reference", "customer", "email", "order", "currency", "fee",
    "category", "sku", "quantity", "qty", "item"
}


def _find_candidate_header(rows: list[Any], max_scan: int = 35) -> int:
    """Find the best row to treat as the header among the top rows."""
    if not rows:
        return 0
    best_idx = 0
    best_score = -1
    for i, r in enumerate(rows[:max_scan]):
        if not r:
            continue
        vals = [str(c).strip() for c in r if c is not None and str(c).strip()]
        if len(vals) < 2:
            continue
        keyword_matches = sum(
            1 for v in vals
            if any(kw in re.sub(r"[^a-zA-Z0-9]", "", v.lower()) for kw in _COMMON_IMPORT_KEYWORDS)
        )
        score = keyword_matches * 10 + min(len(vals), 10)
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx


def _parse_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="The CSV file must be UTF-8 encoded") from exc
    raw_lines = list(csv.reader(io.StringIO(text)))
    if not raw_lines:
        return [], []
    header_idx = _find_candidate_header(raw_lines)
    columns = [str(column).strip() for column in raw_lines[header_idx]]
    columns = [column or f"Column {index + 1}" for index, column in enumerate(columns)]
    rows = []
    for line in raw_lines[header_idx + 1:]:
        if not any(str(c).strip() for c in line):
            continue
        rows.append({columns[i]: str(line[i]).strip() if i < len(line) else "" for i in range(len(columns))})
    return columns, rows


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency installed via requirements
        raise HTTPException(status_code=422, detail="Excel support is not installed on this server") from exc
    try:
        # We explicitly use read_only=False because banking exports often omit sheet dimension XML,
        # which causes openpyxl read_only=True to terminate prematurely after the first row.
        workbook = load_workbook(io.BytesIO(content), read_only=False, data_only=True)
        sheet = workbook.worksheets[0]
        lines = list(sheet.iter_rows(values_only=True))
        workbook.close()
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The Excel file could not be parsed") from exc
    if not lines:
        return [], []
    header_idx = _find_candidate_header(lines)
    columns = [_stringify(value).strip() for value in lines[header_idx]]
    columns = [column or f"Column {index + 1}" for index, column in enumerate(columns)]
    rows: list[dict[str, str]] = []
    for line in lines[header_idx + 1:]:
        values = [_stringify(value) for value in line]
        if not any(value.strip() for value in values):
            continue
        row = {columns[index]: values[index] if index < len(values) else "" for index in range(len(columns))}
        rows.append(row)
    return columns, rows


def _parse_pdf(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    """Extract tables or transaction records from text-based and scanned PDFs."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=422, detail="PDF support is not installed on this server") from exc
    try:
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The PDF file could not be parsed") from exc

    # Strategy 1: Delimited text (comma, tab, pipe, semicolon)
    table = _parse_delimited_pdf_text(text)
    if table is not None:
        return table

    # Strategy 2: Multi-space column-aligned table
    table = _parse_whitespace_table(text)
    if table is not None:
        return table

    # Strategy 3: Invoice / receipt key-value & itemized line-item layout
    table = _parse_invoice_or_receipt_text(text)
    if table is not None:
        return table

    # Strategy 4: Fallback to OCR if configured
    settings = get_settings()
    if not settings.pdf_ocr_enabled:
        raise HTTPException(
            status_code=422,
            detail="Could not find a structured transaction table in this PDF. If this is a scanned document, upload it through the Dashboard with client-side OCR enabled.",
        )
    if len(reader.pages) > settings.pdf_ocr_max_pages:
        raise HTTPException(status_code=422, detail=f"Scanned PDF imports are limited to {settings.pdf_ocr_max_pages} pages")
    return _parse_ocr_pdf(content, settings.pdf_ocr_dpi, settings.pdf_ocr_language)


def _parse_image(content: bytes, filename: str) -> tuple[list[str], list[dict[str, str]]]:
    """Extract commerce and transaction data from images (.png, .jpg, .jpeg, .webp)."""
    text = ""
    try:
        from PIL import Image
        import pytesseract
        img = Image.open(io.BytesIO(content))
        text = pytesseract.image_to_string(img)
    except Exception:
        text = ""

    if text.strip():
        # Check all strategies on recognized text
        for strategy in (_parse_delimited_pdf_text, _parse_whitespace_table, _parse_invoice_or_receipt_text):
            result = strategy(text)
            if result is not None:
                return result

    raise HTTPException(
        status_code=422,
        detail="Image could not be parsed directly on the server. Please upload this image through the Dashboard Import Studio where instant client-side OCR is enabled.",
    )


def _parse_whitespace_table(text: str) -> tuple[list[str], list[dict[str, str]]] | None:
    """Parse text where columns are separated by 2 or more spaces."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None

    for i, line in enumerate(lines[:15]):
        cols = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        if len(cols) >= 2:
            rows: list[dict[str, str]] = []
            for row_line in lines[i + 1:]:
                vals = [p.strip() for p in re.split(r"\s{2,}", row_line) if p.strip()]
                if not vals:
                    continue
                if len(vals) == len(cols):
                    rows.append({cols[c]: vals[c] for c in range(len(cols))})
                elif abs(len(vals) - len(cols)) <= 1 and len(vals) >= 2:
                    row = {cols[c]: vals[c] if c < len(vals) else "" for c in range(len(cols))}
                    rows.append(row)
            if len(rows) >= 1:
                return cols, rows
    return None


def _parse_invoice_or_receipt_text(text: str) -> tuple[list[str], list[dict[str, str]]] | None:
    """Extract structured transaction fields from single-order invoice or receipt text."""
    if not text.strip():
        return None

    # Detect Order / Invoice ID
    order_match = re.search(r"(?:order|invoice|receipt|trans(?:action)?)[\s#.:-]*([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
    order_id = order_match.group(1).strip() if order_match else "INV-001"

    # Detect Date
    date_match = re.search(r"(?:date|dated|time)[\s:]*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})", text, re.IGNORECASE)
    date_val = date_match.group(1).strip() if date_match else datetime.utcnow().strftime("%Y-%m-%d")

    # Detect Customer Email or Name
    cust_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", text)
    if not cust_match:
        cust_match = re.search(r"(?:customer|bill\s+to|client|billed\s+to|buyer)[\s:]*([^\n\r,]+)", text, re.IGNORECASE)
    customer = cust_match.group(1).strip() if cust_match else "customer@example.com"

    # Detect Amount
    amount_matches = re.findall(r"(?:total|amount|grand\s+total|due)[\s:$]*([0-9]+(?:\.[0-9]{2})?)", text, re.IGNORECASE)
    amount = amount_matches[-1] if amount_matches else ""
    if not amount:
        floats = re.findall(r"\$?\s*([0-9]+\.[0-9]{2})", text)
        amount = floats[-1] if floats else "0.00"

    columns = ["order_id", "date", "customer", "revenue", "currency", "status"]
    rows = [
        {
            "order_id": order_id,
            "date": date_val,
            "customer": customer,
            "revenue": amount,
            "currency": "USD",
            "status": "succeeded",
        }
    ]
    return columns, rows


def _parse_delimited_pdf_text(text: str) -> tuple[list[str], list[dict[str, str]]] | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    for delimiter in ("\t", "|", ",", ";"):
        candidate_index = next((index for index, line in enumerate(lines) if line.count(delimiter) >= 1), None)
        if candidate_index is None:
            continue
        table_lines = [line for line in lines[candidate_index:] if line.count(delimiter) >= 1]
        if len(table_lines) < 2:
            continue
        reader = csv.DictReader(io.StringIO("\n".join(table_lines)), delimiter=delimiter)
        columns = [str(column).strip() for column in (reader.fieldnames or [])]
        if len(columns) < 2:
            continue
        rows = [
            {key.strip(): _stringify(value) for key, value in row.items() if key is not None}
            for row in reader
            if any(value is not None and str(value).strip() for value in row.values())
        ]
        if rows:
            return columns, rows
    return None


def _parse_ocr_pdf(content: bytes, dpi: int, language: str) -> tuple[list[str], list[dict[str, str]]]:
    """OCR a scanned PDF only when explicitly enabled in server configuration."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        from pytesseract import TesseractNotFoundError
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Scanned-PDF OCR dependencies are not installed") from exc
    try:
        images = convert_from_bytes(content, dpi=dpi, fmt="png", thread_count=1, timeout=60)
        text = "\n".join(pytesseract.image_to_string(image, lang=language, timeout=30) for image in images)
    except TesseractNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Scanned-PDF OCR is enabled but Tesseract is not installed on the backend host") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The scanned PDF could not be OCR processed") from exc
    table = _parse_delimited_pdf_text(text) or _parse_whitespace_table(text) or _parse_invoice_or_receipt_text(text)
    if table is None:
        raise HTTPException(status_code=422, detail="OCR completed but no transaction table was detected. Use CSV/Excel or a clearer export.")
    return table
