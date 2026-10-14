"""CSV/Excel import API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportBatchRead(BaseModel):
    id: int
    storefront_id: int
    filename: str
    file_kind: str
    status: str
    columns: list[str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    queued_jobs: int = 0
    processing_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    mapping: dict[str, Any] | None = None
    created_at: datetime


class ImportCreated(BaseModel):
    batch: ImportBatchRead
    sample_rows: list[dict[str, Any]]
    suggested_mapping: dict[str, Any]


class MappingSetRequest(BaseModel):
    mapping: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    row: int
    message: str


class ValidationReport(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    issues: list[ValidationIssue]
    preview_payloads: list[dict[str, Any]]


class ImportJobError(BaseModel):
    job_id: int
    source_row: int | None
    message: str | None


class ImportStatusRead(BaseModel):
    batch: ImportBatchRead
    issues: list[ValidationIssue]
    job_errors: list[ImportJobError]
